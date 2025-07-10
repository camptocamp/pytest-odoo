from unittest.mock import MagicMock
common = MagicMock()
from . import case

class BaseCase(case.TestCase):

    def run(*args, **kwargs):
        super().run(*args, **kwargs)
