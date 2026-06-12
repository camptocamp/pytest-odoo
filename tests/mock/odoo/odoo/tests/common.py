from . import case
from unittest.mock import MagicMock

get_db_name = MagicMock()


class BaseCase(case.TestCase):

    def run(self, *args, **kwargs):
        super().run(*args, **kwargs)
        self._call_something()

    def _call_something(self):
        pass


class HttpCase(BaseCase):
    pass
