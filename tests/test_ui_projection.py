from pathlib import Path


HTML = Path(__file__).resolve().parents[1].joinpath("ui", "index.html").read_text()


def test_ui_uses_state_projection_and_honest_empty_copy():
    assert "fetch('/api/state'" in HTML or 'fetch("/api/state"' in HTML
    assert "No ledger events yet" in HTML
    assert "Read-only" in HTML
    assert "No execution" in HTML
    assert "No active positions" in HTML


def test_ui_does_not_claim_live_enabled_protected_or_profitable_fixtures():
    forbidden = ("Service healthy", "Live read", "Entries enabled", "Within daily guardrails", "+0.00%", "Watching")
    for claim in forbidden:
        assert claim not in HTML


def test_ui_has_required_projection_labels_and_jakarta_timestamping():
    for label in ("Kill switch", "Provider", "Market data", "Reconciliation", "Protection", "Latest cycle", "Recent events"):
        assert label in HTML
    assert "Asia/Jakarta" in HTML
    assert "position:sticky" not in HTML
    assert "100vw" not in HTML


def test_ui_evidence_drawer_is_limited_to_approved_fact_labels():
    for label in ("Context hash", "Decision status", "Policy disposition", "Order IDs", "Fill IDs", "Fees", "Funding", "Spread", "Slippage", "Protection evidence", "Reconciliation evidence", "Terminal disposition", "Limitations"):
        assert label in HTML
    assert "api_key" not in HTML.lower()
    assert "access-key" not in HTML.lower()
    assert "fetch('/api/snapshot'" not in HTML


def test_ui_mobile_projection_has_card_layout_and_symmetric_gutters():
    assert "@media(max-width:560px)" in HTML
    assert ".table tr" in HTML
    assert "width:calc(100% - 24px)" in HTML
    assert "overflow-x:hidden" in HTML
