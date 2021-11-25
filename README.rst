pytest-odoo
===========

pytest plugin to run Odoo tests

This lib allows to run the tests built in odoo addons which are using python's unittest, but with the comfort of the pytest CLI. 
Also allowing to run tests without updating given module.

Odoo's `--test-enable` machinery and pytest-odoo do not cover exactly the same scope. The Odoo's test runner runs the tests during
the upgrades of the addons, that's why they need the "at install" and "post install" markers.

Running tests during upgrades of addons is waaay too slow to work efficiently in a TDD mode, that's where pytest-odoo shines.
Consider that all the tests are running post-install with pytest-odoo, as you must run the upgrade of the addon before (but only when needed vs each run).

At the end of the day, its beneficial to run the Odoo tests with --test-enable because, as in very rare conditions,
a test can pass with pytest-odoo but not with the "at install" tests run during the upgrade (or the oposite).
Pytest-odoo can be considered a development tool, but not the tool that should replace entirely --test-enable in a CI.


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

