# -*- coding: utf-8 -*-
# Copyright 2016 Camptocamp SA
# Copyright 2015 Odoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)


import ast
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

import _pytest
import _pytest._py.error as error
import _pytest.python
import odoo
import odoo.tests
import pytest
from _pytest._code.code import ExceptionInfo

def monkey_patch_odoo_meta_model():
    originalMetaModel_new = odoo.models.MetaModel.__new__

    def __monkeypatch_new(self, name, bases, attrs):
        if not attrs.get("__module__", "odoo.addons").startswith("odoo.addons"):
            attrs["__module__"] = f"odoo.addons.{attrs.get('__module__', '')}" 
        return originalMetaModel_new(self, name, bases, attrs) 

    odoo.models.MetaModel.__new__ = __monkeypatch_new


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
    parser.addoption("--odoo-http",
                     action="store_true",
                     help="If pytest should launch an Odoo http server.")
    parser.addoption("--odoo-dev",
                     action="store")
    parser.addoption("--odoo-addons-path",
                     action="store")


@pytest.hookimpl(hookwrapper=True)
def pytest_cmdline_main(config):
    if (config.getoption('--odoo-database')
            or config.getoption('--odoo-config')
            or config.getoption('--odoo-dev')
            or os.environ.get('OPENERP_SERVER')
            or os.environ.get('ODOO_RC')):
        options = []
        # Replace --odoo-<something> by --<something> and prepare the argument
        # to propagate to odoo.
        available_options = [
            '--odoo-database',
            '--odoo-log-level',
            '--odoo-config',
            '--odoo-dev',
            '--odoo-addons-path',
        ]
        for option in available_options:
            value = config.getoption(option)
            if value:
                odoo_arg = '--%s' % option[7:]
                options.append('%s=%s' % (odoo_arg, value))

        # Check the environment variables supported by the Odoo Docker image
        # ref: https://hub.docker.com/_/odoo
        for arg in ['HOST', 'PORT', 'USER', 'PASSWORD']:
            if os.environ.get(arg):
                options.append('--db_%s=%s' % (arg.lower(), os.environ.get(arg)))

        odoo.tools.config.parse_config(options)

        if not odoo.tools.config['db_name']:
            # if you fall here, it means you have ODOO_RC or OPENERP_SERVER pointing
            # to a configuration file without 'database' configuration
            raise Exception(
                "please provide a database name in the Odoo configuration file"
            )

        monkey_patch_odoo_meta_model()
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
    threading.current_thread().testing = True
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


def _find_manifest_path(collection_path: Path) -> Path:
    """Try to locate an Odoo manifest file in the collection path."""
    # check if collection_path is an addon directory
    path = collection_path
    for _ in range(0, 5): 
        if (path.parent / "__manifest__.py").is_file():
            break
        path = path.parent
    else:
        return None
    return path.parent / "__manifest__.py"


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
