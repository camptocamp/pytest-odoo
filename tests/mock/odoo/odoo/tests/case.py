import contextlib


class TestCase:
    
    @contextlib.contextmanager
    def subTest(self, **kwargs):
        """Simulate odoo TestCase.subTest from version 15.0"""


class _Outcome:
    pass