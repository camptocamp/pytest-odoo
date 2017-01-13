# -*- coding: utf-8 -*-
# Copyright 2016 Camptocamp SA
# Copyright 2015 Odoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)

import pytest
import signal
import logging
import os
import sys

import _pytest
import _pytest.python
import py.code
import py.error
import py.path

monkey = None

try:
    from odoo_autodiscover import monkey
except ImportError:  # No odoo_autodiscover
    pass

try:
    import openerp
    # Monkey patch for odoo_autodiscover
    if monkey is not None:
        monkey.patch()
    odoo = openerp
    odoo_namespace = 'openerp'
except ImportError:  # Odoo >= 10.0
    import odoo  # noqa
    odoo_namespace = 'odoo'


@pytest.hookimpl(hookwrapper=True)
def pytest_cmdline_main(config):
    if os.environ.get('OPENERP_SERVER'):
        odoo.tools.config.parse_config([])
        dbname = odoo.tools.config['db_name']
        if not dbname:
            raise Exception(
                "please provide a database name in the Odoo configuration file"
            )
        logging.getLogger(odoo_namespace).setLevel(logging.CRITICAL)
        odoo.service.server.start(preload=[], stop=True)
        # odoo.service.server.start() modifies the SIGINT signal by its own
        # one which in fact prevents us to stop anthem with Ctrl-c.
        # Restore the default one.
        signal.signal(signal.SIGINT, signal.default_int_handler)
        with odoo.api.Environment.manage():
            yield
    else:
        yield


def pytest_pycollect_makemodule(path, parent):
    return OdooTestModule(path, parent)


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
            # for modules in openerp/addons, since there is a __init__ the
            # module name is already fully qualified (maybe?)
            if not modname.startswith(odoo_namespace + '.addons.'):
                modname = odoo_namespace + '.addons.' + modname

            __import__(modname)
            mod = sys.modules[modname]
            if self.fspath.basename == "__init__.py":
                return mod # we don't check anything as we might
                           # we in a namespace package ... too icky to check
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
                "unique basename for your test file modules"
                 % e.args
            )
        self.config.pluginmanager.consider_module(mod)
        return mod
