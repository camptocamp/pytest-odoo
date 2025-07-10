import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from _pytest import pathlib as pytest_pathlib
from pytest_odoo import (
    _find_manifest_path,
    disable_odoo_test_retry,
    monkey_patch_resolve_pkg_root_and_module_name,
    support_subtest,
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

    def test_disable_odoo_test_retry(self):
        from odoo.tests import BaseCase

        original_basecase_run= BaseCase.run

        def restore_basecase_run():
            BaseCase.run = original_basecase_run

        self.addCleanup(restore_basecase_run)

        disable_odoo_test_retry()
        with patch("odoo.tests.BaseCase._call_something") as mock:
            BaseCase().run()
            mock.assert_not_called()


    def test_disable_odoo_test_retry_ignore_run_doesnt_exists(self):
        from odoo.tests import BaseCase

        original_basecase_run= BaseCase.run

        def restore_basecase_run():
            BaseCase.run = original_basecase_run

        self.addCleanup(restore_basecase_run)

        del BaseCase.run

        disable_odoo_test_retry()

        with patch("odoo.tests.BaseCase._call_something") as mock:
            BaseCase().run()
            mock.assert_not_called()

    def test_import_error(self):
        from odoo import tests

        original_BaseCase = tests.BaseCase

        def restore_basecase():
            tests.BaseCase = original_BaseCase

        self.addCleanup(restore_basecase)

        del tests.BaseCase
        disable_odoo_test_retry()

    def test_support_subtest(self):
        from odoo.tests import case

        original_test_case = case.TestCase

        def restore():
            case.TestCase = original_test_case

        self.addCleanup(restore)
        support_subtest()

        from odoo.tests import BaseCase
        from odoo.tests.case import TestCase as OdooTestCase

        self.assertTrue(OdooTestCase.subTest is TestCase.subTest)
        self.assertTrue(BaseCase.subTest is TestCase.subTest)
        self.assertTrue(OdooTestCase.run is TestCase.run)

    def test_support_subtest_import_error(self):
        from odoo.tests import case

        original_odoo_test_case = case.TestCase

        def restore_testcase():
            case.TestCase = original_odoo_test_case

        self.addCleanup(restore_testcase)

        del case.TestCase
        support_subtest()
