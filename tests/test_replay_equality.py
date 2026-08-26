import pytest

from scripts.replay_ledger import ReplayMismatch, assert_replay_equal, replay_events
from src.ledger.sqlite import EventLedger


def test_replay_includes_all_financial_and_safety_dimensions():
    events = [
        {"event_type": "CYCLE_TERMINAL", "payload": {"disposition": "EXECUTED"}},
        {"event_type": "FILL_OBSERVED", "payload": {"symbol": "BTCUSDT", "side": "BUY", "quantity": 1, "price": 100, "fee": 0.2, "funding": -0.1}},
        {"event_type": "PROTECTION_VERIFIED", "payload": {"symbol": "BTCUSDT", "status": "VERIFIED"}},
        {"event_type": "POSITION_RECONCILED", "payload": {"in_sync": True}},
        {"event_type": "RISK_BREAKER_OPEN", "payload": {"reason": "LOSS_LIMIT"}},
        {"event_type": "TRADE_CLOSED", "payload": {"net_pnl": 3, "gross_pnl": 4, "fee": 0.2, "funding": -0.1}},
    ]
    result = replay_events(events)
    assert result["fees"] == pytest.approx(0.2)
    assert result["funding"] == pytest.approx(-0.1)
    assert result["net_pnl"] == pytest.approx(3)
    assert result["risk_breaker"] == "OPEN"
    assert result["reconciliation"] == "IN_SYNC"
    assert result["protection"]["BTCUSDT"] == "VERIFIED"


def test_replay_equality_fails_closed_on_any_terminal_state_drift():
    expected = {"dispositions": {"EXECUTED": 1}, "positions": {}, "protection": {},
                "reconciliation": "UNKNOWN", "risk_breaker": "CLOSED", "fees": 0.0,
                "funding": 0.0, "net_pnl": 0.0, "closed_trades": []}
    with pytest.raises(ReplayMismatch):
        assert_replay_equal(expected, {**expected, "net_pnl": 1.0})


def test_ledger_replay_equality_is_available(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.sqlite3")
    ledger.append_legacy("CYCLE_TERMINAL", {"disposition": "HELD"})
    result = ledger.replay_state()
    assert result["dispositions"] == {"HELD": 1}
    assert result["replay_equal"] is True
