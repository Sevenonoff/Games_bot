import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _journey_from_start(monkeypatch):
    """Виртуальное время тестов — 1970 год: шаги пути считаются с самого начала."""
    from games_core import motivation
    monkeypatch.setattr(motivation, "JOURNEY_EPOCH", 0.0)
