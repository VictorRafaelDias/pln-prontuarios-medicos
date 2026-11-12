"""Garante que os testes não deixem rastros nos dicionários/configurações versionados."""
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nlp import resources  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _preserva_recursos():
    """Tira uma cópia byte a byte de nlp/resources e a restaura ao final (os testes editam dicionários via API)."""
    backup = Path(tempfile.mkdtemp()) / "resources"
    shutil.copytree(resources.RES_DIR, backup)
    yield
    shutil.rmtree(resources.RES_DIR)
    shutil.copytree(backup, resources.RES_DIR)
    resources.reload_resources()
