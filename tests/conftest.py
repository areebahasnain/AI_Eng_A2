"""Each test uses a fresh local ledger; no tests spend real API credits."""
import pytest


@pytest.fixture(autouse=True)
def private_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_PATH", str(tmp_path / "usage.sqlite3"))
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setenv("ALLOW_LIVE_API", "0")
