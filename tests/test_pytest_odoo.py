from unittest import TestCase
import tempfile
from contextlib import contextmanager
from pytest_odoo import _find_manifest_path
from pathlib import Path

class TestPytestOdoo(TestCase):

    @contextmanager
    def fake_module(self):
        directory = tempfile.TemporaryDirectory()
        try:
            module_path = Path(directory.name)
            manifest_path = module_path / "__manifest__.py"
            manifest_path.touch()
            test_path = module_path / "tests" / "test_module.py"
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.touch()
            yield (module_path, manifest_path, test_path,)
        finally:
            directory.cleanup()


    def test_find_manifest_path_less_than_5_directories(self):
        self.assertIsNone(_find_manifest_path(Path("/some/path")))

    def test_find_manifest_path_from_test_module(self):
        with self.fake_module() as (_, manifest_path, test_path):
            self.assertEqual(_find_manifest_path(test_path), manifest_path)

    def test_find_manifest_path_from_itself(self):
        with self.fake_module() as (_, manifest_path, _):
            self.assertEqual(_find_manifest_path(manifest_path), manifest_path)

    def test_find_manifest_path_from_brother(self):
        with self.fake_module() as (module_path, manifest_path, _):
            test = module_path / "test_something.py"
            test.touch()
            self.assertEqual(_find_manifest_path(test), manifest_path)
