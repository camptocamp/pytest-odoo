import contextlib
import importlib
import os
import sys

from pathlib import Path
from types import ModuleType
from typing import Optional, Tuple, Union
from _pytest.compat import assert_never
from _pytest.pathlib import (
    _import_module_using_spec,
    _is_same,
    is_importable,
    resolve_package_path,
    CouldNotResolvePathError,
    ImportMode,
    ImportPathMismatchError,
)


def compute_module_name(root: Path, module_path: Path) -> Optional[str]:
    """Compute a module name based on a path and a root anchor."""
    try:
        path_without_suffix = module_path.with_suffix("")
    except ValueError:
        # Empty paths (such as Path.cwd()) might break meta_path hooks (like our own assertion rewriter).
        return None

    try:
        relative = path_without_suffix.relative_to(root)
    except ValueError:  # pragma: no cover
        return None
    names = list(relative.parts)
    if not names:
        return None
    if names[-1] == "__init__":
        names.pop()
    return "odoo.addons." + ".".join(names)


def module_name_from_path(path: Path, root: Path) -> str:
    """
    Return a dotted module name based on the given path, anchored on root.

    For example: path="projects/src/tests/test_foo.py" and root="/projects", the
    resulting module name will be "src.tests.test_foo".
    """
    path = path.with_suffix("")
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        # If we can't get a relative path to root, use the full path, except
        # for the first part ("d:\\" or "/" depending on the platform, for example).
        path_parts = path.parts[1:]
    else:
        # Use the parts for the relative path to the root path.
        path_parts = relative_path.parts

    # Module name for packages do not contain the __init__ file, unless
    # the `__init__.py` file is at the root.
    if len(path_parts) >= 2 and path_parts[-1] == "__init__":
        path_parts = path_parts[:-1]

    # Module names cannot contain ".", normalize them to "_". This prevents
    # a directory having a "." in the name (".env.310" for example) causing extra intermediate modules.
    # Also, important to replace "." at the start of paths, as those are considered relative imports.
    path_parts = tuple(x.replace(".", "_") for x in path_parts)

    return "odoo.addons" + ".".join(path_parts)


def resolve_pkg_root_and_module_name(
    path: Path, *, consider_namespace_packages: bool = False
) -> Tuple[Path, str]:
    """
    Return the path to the directory of the root package that contains the
    given Python file, and its module name:

        src/
            app/
                __init__.py
                core/
                    __init__.py
                    models.py

    Passing the full path to `models.py` will yield Path("src") and "app.core.models".

    If consider_namespace_packages is True, then we additionally check upwards in the hierarchy
    for namespace packages:

    https://packaging.python.org/en/latest/guides/packaging-namespace-packages

    Raises CouldNotResolvePathError if the given path does not belong to a package (missing any __init__.py files).
    """
    pkg_root: Optional[Path] = None
    pkg_path = resolve_package_path(path)
    if pkg_path is not None:
        pkg_root = pkg_path.parent
    if consider_namespace_packages:
        start = pkg_root if pkg_root is not None else path.parent
        for candidate in (start, *start.parents):
            module_name = compute_module_name(candidate, path)
            if module_name and is_importable(module_name, path):
                # Point the pkg_root to the root of the namespace package.
                pkg_root = candidate
                break

    if pkg_root is not None:
        module_name = compute_module_name(pkg_root, path)
        if module_name:
            return pkg_root, module_name

    raise CouldNotResolvePathError(f"Could not resolve for {path}")


def import_path(
    path: Union[str, "os.PathLike[str]"],
    *,
    mode: Union[str, ImportMode] = ImportMode.prepend,
    root: Path,
    consider_namespace_packages: bool,
) -> ModuleType:
    """
    Import and return a module from the given path, which can be a file (a module) or
    a directory (a package).

    :param path:
        Path to the file to import.

    :param mode:
        Controls the underlying import mechanism that will be used:

        * ImportMode.prepend: the directory containing the module (or package, taking
          `__init__.py` files into account) will be put at the *start* of `sys.path` before
          being imported with `importlib.import_module`.

        * ImportMode.append: same as `prepend`, but the directory will be appended
          to the end of `sys.path`, if not already in `sys.path`.

        * ImportMode.importlib: uses more fine control mechanisms provided by `importlib`
          to import the module, which avoids having to muck with `sys.path` at all. It effectively
          allows having same-named test modules in different places.

    :param root:
        Used as an anchor when mode == ImportMode.importlib to obtain
        a unique name for the module being imported so it can safely be stored
        into ``sys.modules``.

    :param consider_namespace_packages:
        If True, consider namespace packages when resolving module names.

    :raises ImportPathMismatchError:
        If after importing the given `path` and the module `__file__`
        are different. Only raised in `prepend` and `append` modes.
    """
    path = Path(path)
    mode = ImportMode(mode)

    if not path.exists():
        raise ImportError(path)

    if mode is ImportMode.importlib:
        # Try to import this module using the standard import mechanisms, but
        # without touching sys.path.
        try:
            pkg_root, module_name = resolve_pkg_root_and_module_name(
                path, consider_namespace_packages=consider_namespace_packages
            )
            print(f"pkg_root: {pkg_root}, module_name: {module_name}")
        except CouldNotResolvePathError:
            pass
        else:
            # If the given module name is already in sys.modules, do not import it again.
            with contextlib.suppress(KeyError):
                return sys.modules[module_name]

            mod = _import_module_using_spec(
                module_name, path, pkg_root, insert_modules=False
            )
            if mod is not None:
                return mod

        # Could not import the module with the current sys.path, so we fall back
        # to importing the file as a single module, not being a part of a package.
        module_name = module_name_from_path(path, root)
        with contextlib.suppress(KeyError):
            return sys.modules[module_name]

        mod = _import_module_using_spec(
            module_name, path, path.parent, insert_modules=True
        )
        if mod is None:
            raise ImportError(f"Can't find module {module_name} at location {path}")
        return mod

    try:
        pkg_root, module_name = resolve_pkg_root_and_module_name(
            path, consider_namespace_packages=consider_namespace_packages
        )
    except CouldNotResolvePathError:
        pkg_root, module_name = path.parent, path.stem

    # Change sys.path permanently: restoring it at the end of this function would cause surprising
    # problems because of delayed imports: for example, a conftest.py file imported by this function
    # might have local imports, which would fail at runtime if we restored sys.path.
    if mode is ImportMode.append:
        if str(pkg_root) not in sys.path:
            sys.path.append(str(pkg_root))
    elif mode is ImportMode.prepend:
        if str(pkg_root) != sys.path[0]:
            sys.path.insert(0, str(pkg_root))
    else:
        assert_never(mode)

    importlib.import_module(module_name)

    mod = sys.modules[module_name]
    if path.name == "__init__.py":
        return mod

    ignore = os.environ.get("PY_IGNORE_IMPORTMISMATCH", "")
    if ignore != "1":
        module_file = mod.__file__
        if module_file is None:
            raise ImportPathMismatchError(module_name, module_file, path)

        if module_file.endswith((".pyc", ".pyo")):
            module_file = module_file[:-1]
        if module_file.endswith(os.sep + "__init__.py"):
            module_file = module_file[: -(len(os.sep + "__init__.py"))]

        try:
            is_same = _is_same(str(path), module_file)
        except FileNotFoundError:
            is_same = False

        if not is_same:
            raise ImportPathMismatchError(module_name, module_file, path)

    return mod
