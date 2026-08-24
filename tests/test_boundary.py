from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TEXT = ("/opt/bots/bitget-listener", "/root/bitget-listener")


def test_runtime_source_does_not_reference_live_bot_paths():
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text()
        assert not any(value in text for value in FORBIDDEN_TEXT), path


def test_runtime_source_has_no_exchange_secret_defaults():
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text()
        assert "BITGET_API_KEY=" not in text
        assert "BITGET_SECRET=" not in text
        assert "BITGET_PASSPHRASE=" not in text


def test_boundary_document_exists():
    doc = ROOT / "docs" / "INTEGRATION_BOUNDARY.md"
    assert doc.is_file()
    assert "standalone" in doc.read_text().lower()
