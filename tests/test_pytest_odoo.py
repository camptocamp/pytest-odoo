import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase

from _pytest import pathlib as pytest_pathlib
from pytest_odoo import (
    _find_manifest_path,
    monkey_patch_resolve_pkg_root_and_module_name,
)


class TestPytestOdoo(TestCase):

    @contextmanager
    def fake_module(self, with_manifest=True,  using_addons_namespace=False):
        directory = tempfile.TemporaryDirectory()
        try:
            module_path = Path(directory.name)
            files = []
            if using_addons_namespace:
                files.append(module_path / "odoo" / "__init__.py")
                files.append(module_path / "odoo" / "addons" / "__init__.py")
                module_path = module_path / "odoo" / "addons" / "my_module"
                module_path.mkdir(parents=True, exist_ok=True)
            manifest_path = None
            if with_manifest:
                manifest_path = module_path / "__manifest__.py"
                files.append(manifest_path)
            test_path = module_path / "tests" / "test_module.py"
            test_path.parent.mkdir(parents=True, exist_ok=True)
            files.append(test_path)
            files.append(module_path / "__init__.py")
            files.append(module_path / "tests" / "__init__.py")
            for file_path in files:
                file_path.touch()
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

    def test_resolve_pkg_root_and_module_name(self):
        monkey_patch_resolve_pkg_root_and_module_name()
        with self.fake_module() as (module_path, _, test_path):
            pkg_root, module_name = pytest_pathlib.resolve_pkg_root_and_module_name(test_path)
            self.assertEqual(
                module_name,
                f"odoo.addons.{module_path.name}.tests.test_module"
            )

    def test_resolve_pkg_root_and_module_name_not_odoo_module(self):
        monkey_patch_resolve_pkg_root_and_module_name()

        with self.fake_module(with_manifest=False) as (module_path, _, test_path):
            pkg_root, module_name = pytest_pathlib.resolve_pkg_root_and_module_name(test_path)
            self.assertEqual(
                module_name,
                f"{module_path.name}.tests.test_module"
            )

    def test_resolve_pkg_root_and_module_name_namespace_ok(self):
        monkey_patch_resolve_pkg_root_and_module_name()

        with self.fake_module(with_manifest=True, using_addons_namespace=True) as (module_path, _, test_path):
            pkg_root, module_name = pytest_pathlib.resolve_pkg_root_and_module_name(test_path)
            self.assertEqual(
                module_name,
                "odoo.addons.my_module.tests.test_module"
            )
