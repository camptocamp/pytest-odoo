from odoo import http
from odoo.http import request


class PytestOdooTestController(http.Controller):

    @http.route("/pytest-odoo/test", auth="user", type="http")
    def test(self):
        return "Hello World"
