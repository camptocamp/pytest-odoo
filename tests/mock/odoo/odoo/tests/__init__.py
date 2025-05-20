from unittest.mock import MagicMock
common = MagicMock()


class BaseCase:

    def run(*args, **kwargs):
        super().run(*args, **kwargs)
