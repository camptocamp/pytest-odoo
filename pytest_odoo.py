# -*- coding: utf-8 -*-
# Copyright 2016 Camptocamp SA
# Copyright 2015 Odoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)


import os
import signal
import sys
import threading

import _pytest
import _pytest.python
import py.code
import py.error
import py.path
import pytest

try:
    import openerp
    odoo = openerp
    odoo_namespace = 'openerp'
except ImportError:  # Odoo >= 10.0
    import odoo  # noqa
    odoo_namespace = 'odoo'


def pytest_addoption(parser):
    parser.addoption("--odoo-database",
                     action="store",
                     help="Name of the Odoo database to test")
    parser.addoption("--odoo-config",
                     action="store",
                     help="Path of the Odoo configuration file")
    parser.addoption("--odoo-log-level",
                     action="store",
                     default='critical',
                     help="Log-level used by the Odoo process during tests")


@pytest.hookimpl(hookwrapper=True)
def pytest_cmdline_main(config):

    if (config.getoption('--odoo-database')
            or config.getoption('--odoo-config')
            or os.environ.get('OPENERP_SERVER')
            or os.environ.get('ODOO_RC')):
        options = []
        # Replace --odoo-<something> by --<something> and prepare the argument
        # to propagate to odoo.
        for option in ['--odoo-database', '--odoo-log-level', '--odoo-config']:
            value = config.getoption(option)
            if value:
                odoo_arg = '--%s' % option[7:]
                options.append('%s=%s' % (odoo_arg, value))

        odoo.tools.config.parse_config(options)

        if not odoo.tools.config['db_name']:
            # if you fall here, it means you have OPENERP_SERVER pointing
            # to a configuration file without 'database' configuration
            raise Exception(
                "please provide a database name in the Odoo configuration file"
            )

        odoo.service.server.start(preload=[], stop=True)
        # odoo.service.server.start() modifies the SIGINT signal by its own
        # one which in fact prevents us to stop anthem with Ctrl-c.
        # Restore the default one.
        signal.signal(signal.SIGINT, signal.default_int_handler)
        with odoo.api.Environment.manage():
            yield
    else:
        yield


@pytest.fixture(scope='session', autouse=True)
def load_registry():
    # Initialize the registry before running tests.
    # If we don't do that, the modules will be loaded *inside* of the first
    # test we run, which would trigger the launch of the postinstall tests
    # (because we force 'test_enable' to True and the at end of the loading of
    # the registry, the postinstall tests are run when test_enable is enabled).
    # And also give wrong timing indications.
    # Finally we enable `testing` flag on current thread
    # since Odoo sets it when loading test suites.
    threading.currentThread().testing = True
    odoo.registry(odoo.tests.common.get_db_name())


@pytest.fixture(scope='module', autouse=True)
def enable_odoo_test_flag():
    # When we run tests through Odoo, test_enable is always activated, and some
    # code might rely on this (for instance to selectively disable database
    # commits). When we run the tests through pytest, the flag is not
    # activated, and if it was activated globally, it would make odoo start all
    # tests in addition to the tests we are running through pytest.  If we
    # enable the option only in the scope of the tests modules, we won't
    # interfere with the odoo's loading of modules, thus we are good.
    odoo.tools.config['test_enable'] = True
    yield
    odoo.tools.config['test_enable'] = False


# Original code of xmo-odoo:
# https://github.com/odoo-dev/odoo/commit/95a131b7f4eebc6e2c623f936283153d62f9e70f
class OdooTestModule(_pytest.python.Module):
    """ Should only be invoked for paths inside Odoo addons
    """

    def _importtestmodule(self):
        # copy/paste/modified from original: removed sys.path injection &
        # added Odoo module prefixing so import within modules is correct
        try:
            pypkgpath = self.fspath.pypkgpath()
            pkgroot = pypkgpath.dirpath()
            sep = self.fspath.sep
            names = self.fspath.new(ext="").relto(pkgroot).split(sep)
            if names[-1] == "__init__":
                names.pop()
            modname = ".".join(names)
            # modules installed with pip for odoo<=9 are into the
            # odoo_addons namespace. Makes module part of the odoo namespace
            if modname.startswith('odoo_addons'):
                modname = odoo_namespace + '.addons.' + modname.replace(
                    'odoo_addons.', '')
            # for modules in openerp/addons, since there is a __init__ the
            # module name is already fully qualified (maybe?)
            if (not modname.startswith(odoo_namespace + '.addons.')
                    and modname != odoo_namespace + '.addons'
                    and modname != odoo_namespace):
                modname = odoo_namespace + '.addons.' + modname

            __import__(modname)
            mod = sys.modules[modname]
            if self.fspath.basename == "__init__.py":
                # we don't check anything as we might
                # we in a namespace package ... too icky to check
                return mod
            modfile = mod.__file__
            if modfile[-4:] in ('.pyc', '.pyo'):
                modfile = modfile[:-1]
            elif modfile.endswith('$py.class'):
                modfile = modfile[:-9] + '.py'
            if modfile.endswith(os.path.sep + "__init__.py"):
                if self.fspath.basename != "__init__.py":
                    modfile = modfile[:-12]
            try:
                issame = self.fspath.samefile(modfile)
            except py.error.ENOENT:
                issame = False
            if not issame:
                raise self.fspath.ImportMismatchError(modname, modfile, self)
        except SyntaxError:
            raise self.CollectError(
                py.code.ExceptionInfo().getrepr(style="short"))
        except self.fspath.ImportMismatchError:
            e = sys.exc_info()[1]
            raise self.CollectError(
                "import file mismatch:\n"
                "imported module %r has this __file__ attribute:\n"
                "  %s\n"
                "which is not the same as the test file we want to collect:\n"
                "  %s\n"
                "HINT: remove __pycache__ / .pyc files and/or use a "
                "unique basename for your test file modules" % e.args
            )
        self.config.pluginmanager.consider_module(mod)
        return mod

    def __repr__(self):
        return "<Module %r>" % (getattr(self, "name", None), )


class OdooTestPackage(_pytest.python.Package, OdooTestModule):
    """Package with odoo module lookup.

    Any python module inside the package will be imported with
    the prefix `odoo.addons`.

    This class is used to prevent loading odoo modules in duplicate,
    which happens if a module is loaded with and without the prefix.
    """

    def __repr__(self):
        return "<Package %r>" % (getattr(self, "name", None), )


def supports_from_parent(node):
    """ Check if pytest supports from_parent constructor

    Node Construction changed to Node.from_parent in pytest 5.4
    """
    if hasattr(node, "from_parent"):
        return True


def pytest_pycollect_makemodule(path, parent):
    if path.basename == "__init__.py":
        if supports_from_parent(OdooTestPackage):
            return OdooTestPackage.from_parent(parent, fspath=path)
        return OdooTestPackage(path, parent)
    else:
        if supports_from_parent(OdooTestModule):
            return OdooTestModule.from_parent(parent, fspath=path)
        return OdooTestModule(path, parent)
