try:
    from odoo.tests.common import SavepointCase as TransactionCase
except ImportError:
    from odoo.tests.common import TransactionCase


class TestModuleCommon(TransactionCase):
    def test_subtest(self):

        with self.subTest("subtest 1"):
            self.assertTrue(True)
        with self.subTest("subtest 2"):
            self.assertTrue(True)
