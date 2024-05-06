# -*- coding: utf-8 -*-
# Copyright 2016 Camptocamp SA
# Copyright 2015 Odoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)


import ast
import contextlib
import importlib
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional, Tuple, Union
from types import ModuleType

import odoo
import odoo.tests
import odoo.tools.config
import pytest

from functools import partial
from _pytest import nodes
from _pytest._code.code import filter_traceback, ExceptionInfo
from _pytest.config import Config
from _pytest.compat import assert_never
from _pytest.outcomes import skip
from _pytest.pathlib import (
    _import_module_using_spec,
    _is_same,
    is_importable,
    resolve_package_path,
    CouldNotResolvePathError,
    ImportMode,
    ImportPathMismatchError,
)
from _pytest.python import (
    Module,
    Package,
    _call_with_optional_argument,
    _get_first_non_fixture_func,
)


def pytest_addoption(parser):
    parser.addoption(
        "--odoo-database", action="store", help="Name of the Odoo database to test"
    )
    parser.addoption(
        "--odoo-config", action="store", help="Path of the Odoo configuration file"
    )
    parser.addoption(
        "--odoo-log-level",
        action="store",
        default="critical",
        help="Log-level used by the Odoo process during tests",
    )
    parser.addoption(
        "--odoo-http",
        action="store_true",
        help="If pytest should launch an Odoo http server.",
    )
    parser.addoption("--odoo-dev", action="store")
    parser.addoption("--odoo-addons-path", action="store")
    parser.addoption("--odoo-ignore-env", action="store_true")


def compute_module_name(root: Path, module_path: Path) -> Optional[str]:
    """Compute a module name based on a path and a root anchor.
    This method is an adaption of
    https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/pathlib.py#L862
    to match odoo name binding."""
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

    This method is an adaption of
    https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/pathlib.py#L706
    to match odoo name binding.
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

    This method is an adaption of
    https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/pathlib.py#L792
    to match odoo name binding through the adapted compute_module_name function.
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

    This method is an adaption of
    https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/pathlib.py#L493
    to match odoo name binding through the adapted resolve_pkg_root_and_module_name and module_name_from_path functions.
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


@pytest.hookimpl(hookwrapper=True)
def pytest_cmdline_main(config):
    if (
        config.getoption("--odoo-database")
        or config.getoption("--odoo-config")
        or config.getoption("--odoo-dev")
        or os.environ.get("OPENERP_SERVER")
        or os.environ.get("ODOO_RC")
    ):
        options = []
        # Replace --odoo-<something> by --<something> and prepare the argument
        # to propagate to odoo.
        available_options = [
            "--odoo-database",
            "--odoo-log-level",
            "--odoo-config",
            "--odoo-dev",
            "--odoo-addons-path",
        ]
        for option in available_options:
            value = config.getoption(option)
            if value:
                odoo_arg = "--%s" % option[7:]
                options.append("%s=%s" % (odoo_arg, value))

        # Check the environment variables supported by the Odoo Docker image
        # ref: https://hub.docker.com/_/odoo
        if not config.getoption("--odoo-ignore-env"):
            for arg in ["HOST", "PORT", "USER", "PASSWORD"]:
                if os.environ.get(arg):
                    options.append("--db_%s=%s" % (arg.lower(), os.environ.get(arg)))

        odoo.tools.config.parse_config(options)

        if not odoo.tools.config["db_name"]:
            # if you fall here, it means you have ODOO_RC or OPENERP_SERVER pointing
            # to a configuration file without 'database' configuration
            raise Exception(
                "please provide a database name in the Odoo configuration file"
            )

        odoo.service.server.start(preload=[], stop=True)
        # odoo.service.server.start() modifies the SIGINT signal by its own
        # one which in fact prevents us to stop anthem with Ctrl-c.
        # Restore the default one.
        signal.signal(signal.SIGINT, signal.default_int_handler)

        if odoo.release.version_info < (15,):
            # Refactor in Odoo 15, not needed anymore
            with odoo.api.Environment.manage():
                yield
        else:
            yield
    else:
        yield


@pytest.fixture(scope="module", autouse=True)
def load_http(request):
    if request.config.getoption("--odoo-http"):
        odoo.service.server.start(stop=True)
        signal.signal(signal.SIGINT, signal.default_int_handler)


@pytest.fixture(scope="session", autouse=True)
def load_registry():
    # Initialize the registry before running tests.
    # If we don't do that, the modules will be loaded *inside* of the first
    # test we run, which would trigger the launch of the postinstall tests
    # (because we force 'test_enable' to True and the at end of the loading of
    # the registry, the postinstall tests are run when test_enable is enabled).
    # And also give wrong timing indications.
    # Finally we enable `testing` flag on current thread
    # since Odoo sets it when loading test suites.
    threading.current_thread().testing = True
    odoo.registry(odoo.tests.common.get_db_name())


@pytest.fixture(scope="module", autouse=True)
def enable_odoo_test_flag():
    # When we run tests through Odoo, test_enable is always activated, and some
    # code might rely on this (for instance to selectively disable database
    # commits). When we run the tests through pytest, the flag is not
    # activated, and if it was activated globally, it would make odoo start all
    # tests in addition to the tests we are running through pytest.  If we
    # enable the option only in the scope of the tests modules, we won't
    # interfere with the odoo's loading of modules, thus we are good.
    odoo.tools.config["test_enable"] = True
    yield
    odoo.tools.config["test_enable"] = False


def importtestmodule(
    path: Path,
    config: Config,
):
    """Adapted function of
    https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/python.py#L480"""
    # We assume we are only called once per module.
    importmode = config.getoption("--import-mode")
    try:
        mod = import_path(
            path,
            mode=importmode,
            root=config.rootpath,
            consider_namespace_packages=config.getini("consider_namespace_packages"),
        )
    except SyntaxError as e:
        raise nodes.Collector.CollectError(
            ExceptionInfo.from_current().getrepr(style="short")
        ) from e
    except ImportPathMismatchError as e:
        raise nodes.Collector.CollectError(
            "import file mismatch:\n"
            "imported module {!r} has this __file__ attribute:\n"
            "  {}\n"
            "which is not the same as the test file we want to collect:\n"
            "  {}\n"
            "HINT: remove __pycache__ / .pyc files and/or use a "
            "unique basename for your test file modules".format(*e.args)
        ) from e
    except ImportError as e:
        exc_info = ExceptionInfo.from_current()
        if config.getoption("verbose") < 2:
            exc_info.traceback = exc_info.traceback.filter(filter_traceback)
        exc_repr = (
            exc_info.getrepr(style="short")
            if exc_info.traceback
            else exc_info.exconly()
        )
        formatted_tb = str(exc_repr)
        raise nodes.Collector.CollectError(
            f"ImportError while importing test module '{path}'.\n"
            "Hint: make sure your test modules/packages have valid Python names.\n"
            "Traceback:\n"
            f"{formatted_tb}"
        ) from e
    except skip.Exception as e:
        if e.allow_module_level:
            raise
        raise nodes.Collector.CollectError(
            "Using pytest.skip outside of a test will skip the entire module. "
            "If that's your intention, pass `allow_module_level=True`. "
            "If you want to skip a specific test or an entire class, "
            "use the @pytest.mark.skip or @pytest.mark.skipif decorators."
        ) from e
    config.pluginmanager.consider_module(mod)
    return mod


class OdooTestModule(Module):
    """Should only be invoked for paths inside Odoo addons
    Original at https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/python.py#L536
    """

    def _getobj(self):
        return importtestmodule(self.path, self.config)


class OdooTestPackage(Package):
    """Package with odoo module lookup.

    Any python module inside the package will be imported with
    the prefix `odoo.addons`.

    This class is used to prevent loading odoo modules in duplicate,
    which happens if a module is loaded with and without the prefix.

    Original at https://github.com/pytest-dev/pytest/blob/6bd3f313447290380cbc2db30fb9ee5cca7eb941/src/_pytest/python.py#L619
    """

    def setup(self) -> None:
        init_mod = importtestmodule(self.path / "__init__.py", self.config)

        # Not using fixtures to call setup_module here because autouse fixtures
        # from packages are not called automatically (#4085).
        setup_module = _get_first_non_fixture_func(
            init_mod, ("setUpModule", "setup_module")
        )
        if setup_module is not None:
            _call_with_optional_argument(setup_module, init_mod)

        teardown_module = _get_first_non_fixture_func(
            init_mod, ("tearDownModule", "teardown_module")
        )
        if teardown_module is not None:
            func = partial(_call_with_optional_argument, teardown_module, init_mod)
            self.addfinalizer(func)


@pytest.hookimpl()
def pytest_pycollect_makemodule(module_path, path, parent):
    if not _find_manifest_path(module_path):
        return None
    return OdooTestModule.from_parent(parent, path=Path(path))


@pytest.hookimpl()
def pytest_collect_directory(path, parent):
    if not _find_manifest_path(path):
        return None
    pkginit = path / "__init__.py"
    if pkginit.is_file():
        return OdooTestPackage.from_parent(parent, path=path)
    return None


def _find_manifest_path(collection_path: Path) -> Path | None:
    """Try to locate an Odoo manifest file in the collection path."""
    # check if collection_path is an addon directory
    path = collection_path
    level = 0
    while level < 5 and not (path / "__manifest__.py").is_file():
        path = path.parent
        level += 1
    if not (path / "__manifest__.py").is_file():
        return None
    return path / "__manifest__.py"


def pytest_ignore_collect(collection_path: Path) -> Optional[bool]:
    """Do not collect tests of modules that are marked non installable."""
    manifest_path = _find_manifest_path(collection_path)
    if not manifest_path:
        return None
    manifest = ast.literal_eval(manifest_path.read_text())
    if not manifest.get("installable", True):
        # installable = False, do not collect this
        return True
    return None
