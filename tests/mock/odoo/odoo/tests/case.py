import contextlib


class TestCase:

    @contextlib.contextmanager
    def subTest(self, **kwargs):
        """Simulate odoo TestCase.subTest from version 15.0"""

    def run(self, *args, **kwargs):
        self._call_a_method()

    def _call_a_method(self):
        pass
