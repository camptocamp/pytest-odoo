pytest-odoo
===========

pytest plugin to run Odoo tests

This lib allows to run the tests built in Odoo addons which are using Python's `unittest <https://docs.python.org/3/library/unittest.html>`_, but with the comfort of the `pytest <https://docs.pytest.org/>`_ CLI. 
Also allowing to run tests without updating given module.

Odoo's `--test-enable` machinery and pytest-odoo do not cover exactly the same scope. The Odoo's test runner runs the tests during
the upgrades of the addons, that's why they need the "at install" and "post install" markers.

Running tests during upgrades of addons is waaay too slow to work efficiently in a TDD mode, that's where pytest-odoo shines.
Consider that all the tests are running `post-install` with pytest-odoo, as you must run the upgrade of the addon before (but only when needed vs each run).

At the end of the day, its beneficial to run the Odoo tests with `--test-enable` because, as in very rare conditions,
a test can pass with pytest-odoo but not with the "at install" tests run during the upgrade (or the oposite).
Pytest-odoo can be considered a development tool, but not the tool that should replace entirely `--test-enable` in a CI.

See also the `official Odoo documentation <https://www.odoo.com/documentation/15.0/developer/reference/backend/testing.html#testing-python-code>`_ on writing tests.

Usage
-----

install via::

    pip install pytest-odoo

usage::

   pytest -s --odoo-database=test --odoo-log-level=debug_sql [--odoo-http]

The custom options are:

* ``--odoo-database``: name of the database to test.
* ``--odoo-log-level``: log level as expected by odoo. As time of writing: info, debug_rpc, warn, test, critical, debug_sql, error, debug, debug_rpc_answer. The default is critical to have a clean output.
* ``--odoo-config``: path of the odoo.cfg file to use.
* ``--odoo-http``: Allow to launch the Odoo http instance


Alternatively, you can use environment variables, like the Odoo Docker image:

* ``HOST``: hostname of the database server
* ``PORT``: port of the database server
* ``USER``: username to access the database
* ``PASSWORD``: password to access the database

These only work in addition to ``--odoo-database``.

You can use the ``ODOO_RC`` environment variable using an odoo configuration file, containing at least the ``database`` option with the name of the database to test::

   export ODOO_RC=/path/to/odoo/config.cfg
   pytest ...


Known issues
------------

Currently not compatible with pytest >= 8.0.0
