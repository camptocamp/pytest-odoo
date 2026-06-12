from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def res_partner_test_method(self):
        return True
