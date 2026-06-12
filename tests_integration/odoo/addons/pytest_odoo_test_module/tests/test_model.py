try:
    from odoo.tests.common import SavepointCase as TransactionCase
except ImportError:
    from odoo.tests.common import TransactionCase


class TestModuleCommon(TransactionCase):
    def test_res_partner_test_method(self):
        self.assertTrue(self.env["res.partner"].res_partner_test_method())
