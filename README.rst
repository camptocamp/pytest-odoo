pytest-odoo
===========

pytest plugin to run Odoo tests

Usage
-----

install via::

    pip install pytest-odoo

usage::

   export OPENERP_SERVER=/path/to/odoo/config.cfg
   pytest ...

The path of the Odoo configuration file must be set in the ``OPENERP_SERVER``
environment variable. The configuration file must contain the name of the
database on which the tests are run.
