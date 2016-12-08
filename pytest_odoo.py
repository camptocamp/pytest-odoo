# -*- coding: utf-8 -*-
# Copyright 2016 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)

import pytest
import signal
import logging
import os

try:
    import openerp as odoo
    odoo_logger = 'openerp'
except ImportError:  # Odoo >= 10.0
    import odoo  # noqa
    odoo_logger = 'odoo'


@pytest.hookimpl(hookwrapper=True)
def pytest_cmdline_main(config):
    if os.environ.get('OPENERP_SERVER'):
        odoo.tools.config.parse_config([])
        dbname = odoo.tools.config['db_name']
        if not dbname:
            raise Exception(
                "please provide a database name though Odoo options (either "
                "-d or an Odoo configuration file)"
            )
        logging.getLogger(odoo_logger).setLevel(logging.CRITICAL)
        odoo.service.server.start(preload=[], stop=True)
        # odoo.service.server.start() modifies the SIGINT signal by its own
        # one which in fact prevents us to stop anthem with Ctrl-c.
        # Restore the default one.
        signal.signal(signal.SIGINT, signal.default_int_handler)
        with odoo.api.Environment.manage():
            yield
    else:
        yield

