from src.ledger.sqlite import EventLedger
from scripts.replay_ledger import replay_events


def test_replay_rebuilds_terminal_dispositions_and_positions(tmp_path):
    ledger = EventLedger(tmp_path / "events.sqlite3")
    ledger.append("AGENT_DECISION", {"cycle_id": "c1", "action": "ENTER", "symbol": "BTCUSDT", "side": "BUY"})
    ledger.append("FILL_OBSERVED", {"cycle_id": "c1", "symbol": "BTCUSDT", "side": "BUY", "quantity": 1, "price": 100, "fee": 0.05})
    ledger.append("PROTECTION_VERIFIED", {"cycle_id": "c1", "symbol": "BTCUSDT", "status": "VERIFIED"})
    ledger.append("CYCLE_TERMINAL", {"cycle_id": "c1", "disposition": "EXECUTED"})
    result = replay_events(ledger.all())
    assert result["dispositions"] == {"EXECUTED": 1}
    assert result["positions"]["BTCUSDT"]["quantity"] == 1
    assert result["positions"]["BTCUSDT"]["protection"] == "VERIFIED"


def test_replay_preserves_parked_risk_breaker_state(tmp_path):
    ledger = EventLedger(tmp_path / "events.sqlite3")
    ledger.append("RISK_BREAKER_OPEN", {"reason": "LOSS_LIMIT"})
    ledger.append("CYCLE_TERMINAL", {"cycle_id": "c2", "disposition": "PARKED_RISK"})
    result = replay_events(ledger.all())
    assert result["risk_breaker"] == "OPEN"
    assert result["dispositions"]["PARKED_RISK"] == 1
