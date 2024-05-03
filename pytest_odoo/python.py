from pytest_odoo.pathlib import import_path

from functools import partial
from pathlib import Path
from _pytest import nodes
from _pytest._code import filter_traceback
from _pytest._code.code import ExceptionInfo
from _pytest.config import Config
from _pytest.outcomes import skip
from _pytest.pathlib import ImportPathMismatchError
from _pytest.python import (
    Module,
    Package,
    _call_with_optional_argument,
    _get_first_non_fixture_func,
)


def importtestmodule(
    path: Path,
    config: Config,
):
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


class OdooTestPackage(Package):
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


class OdooTestModule(Module):
    def _getobj(self):
        return importtestmodule(self.path, self.config)
