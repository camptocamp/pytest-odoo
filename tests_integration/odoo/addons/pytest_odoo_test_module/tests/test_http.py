import unittest
import odoo
try:
    from odoo.addons.base.tests.common import HttpCaseWithUserDemo as HttpCase
except ImportError:
    from odoo.tests.common import HttpCase


class TestModuleCommon(HttpCase):

    def test_pytest_endpoints(self):
        self.authenticate("demo", "demo")
        result = self.url_open("/pytest-odoo/test", allow_redirects=False)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.text, "Hello World")
