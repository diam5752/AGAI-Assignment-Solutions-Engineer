"""Pytest configuration to make the local package importable without installation."""
import json
import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path for module resolution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.cli import main as cli_main
from automation.extractors import load_records


@pytest.fixture(autouse=True)
def disable_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable remote LLM calls during tests to avoid token usage."""

    monkeypatch.setenv("AI_ENRICHMENT_DISABLED", "1")


@pytest.fixture
def dummy_data_dir() -> Path:
    """Return the built-in dummy data directory for tests."""

    return ROOT / "dummy_data"


@pytest.fixture
def expected_record_count(dummy_data_dir: Path) -> int:
    """Provide the number of raw records in the dummy data folder."""

    return len(load_records(dummy_data_dir))


@pytest.fixture
def fake_service_account_file(tmp_path: Path) -> Path:
    """Create a stub Google service account file for Sheets tests."""

    credentials = {
        "type": "service_account",
        "client_email": "test@example.com",
        "private_key_id": "dummy",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIBVw==\n-----END PRIVATE KEY-----\n",
    }
    path = tmp_path / "service_account.json"
    path.write_text(json.dumps(credentials), encoding="utf-8")
    return path


@pytest.fixture
def run_cli(monkeypatch: pytest.MonkeyPatch):
    """Helper to invoke the CLI with custom arguments inside tests."""

    def _run(args: list[str]) -> None:
        monkeypatch.setattr(sys, "argv", ["automation.cli", *args])
        cli_main()

    return _run
