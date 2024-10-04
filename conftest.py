import sys
import types

sys.modules["odoo"] = types.ModuleType("odoo")
sys.modules["odoo.tests"] = types.ModuleType("odoo.tests")
