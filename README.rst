pytest-odoo
===========

pytest plugin to run Odoo tests

Usage
-----

install via::

    pip install pytest-odoo

usage::

   pytest -s --odoo-database=test --odoo-log-level=debug_sql

The custom options are:

* ``--odoo-database``: name of the database to test.
* ``--odoo-log-level``: log level as expected by odoo. As time of writing: info, debug_rpc, warn, test, critical, debug_sql, error, debug, debug_rpc_answer. The default is critical to have a clean output.
* ``--odoo-config``: path of the odoo.cfg file to use.

Alternatively, you can use the ``OPENERP_SERVER`` environment variable using an odoo configuration file, containing at least the ``database`` option with the name of the database to test::

   export OPENERP_SERVER=/path/to/odoo/config.cfg
   pytest ...

