import json
from pathlib import Path

import pytest

from core.db import get_engine, init_db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def history_response() -> dict:
    return json.loads((FIXTURES / "history_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def engine(tmp_path):
    return init_db(get_engine(f"sqlite:///{tmp_path / 'test.db'}"))
