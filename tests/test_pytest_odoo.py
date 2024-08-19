from pytest_odoo import _find_manifest_path
from pathlib import Path


def test_find_manifest_path():
    
    assert _find_manifest_path(Path("/some/path")) is None