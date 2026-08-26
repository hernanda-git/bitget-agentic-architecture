"""Bounded, offline autonomous paper runner. It never creates signed requests."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.context import PortfolioView
from src.agentic_engine import Policy
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import MarketSnapshot
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse
from src.paper_loop import PaperLoop
from src.reporting import write_run_report
from src.simulation.events import MarketEvent
from src.health.variation import assess_runtime_health


def _response(symbol: str, scenario: str, now: int) -> ProviderResponse:
    if scenario == "enter":
        body = {"decision_id": "offline-enter-001", "action": "ENTER", "symbol": symbol,
                "side": "BUY", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
                "leverage": 1, "max_notional_usd": 100, "valid_until_ms": now + 60_000,
                "thesis": "offline fixture", "invalidation": "below stop"}
    else:
        body = {"decision_id": "offline-hold-001", "action": "HOLD", "symbol": symbol,
                "side": "NONE", "entry": None, "stop_loss": None, "take_profit": None,
                "leverage": 1, "max_notional_usd": 1, "valid_until_ms": now + 60_000,
                "thesis": "offline fixture", "invalidation": "fixture ended"}
    return ProviderResponse(status="OK", content=json.dumps(body), provider="fake", model="fixture", prompt_version="offline-v1")


def run_paper(cycles: int, symbols: list[str], ledger_path: Path, reports_dir: Path,
              scenario: str = "hold", inject_integrity_failure: bool = False) -> dict:
    if cycles < 1 or not symbols:
        raise ValueError("cycles and symbols must be non-empty")
    ledger = EventLedger(ledger_path)
    venue = FakeExchange()
    policy = Policy(frozenset(symbols), 3, 1_000, 50, 10, kill_switch=False)
    events_before = len(ledger.all())
    results = []
    market_marks = []
    decision_statuses = []
    now = int(time.time() * 1000)
    for index in range(cycles):
        for symbol in symbols:
            snapshot = MarketSnapshot(symbol, 100, 99.99, 100.01, 0, 1, now + index, now + index).with_hash()
            market_marks.append(snapshot.mark_price)
            provider = FakeProvider([_response(symbol, scenario, now + index)])
            result = asyncio.run(PaperLoop(provider, policy, ledger, venue).process(
                snapshot, PortfolioView(), now + index))
            decision_statuses.append(result.get("status", "UNKNOWN"))
            # A bounded paper cycle includes the market path to a terminal exit.
            # This is deliberately deterministic and remains entirely offline.
            if scenario == "enter" and symbol in venue.positions:
                position = venue.positions[symbol]
                target = position.take_profit or 110.0
                exits = venue.apply_market_event(MarketEvent(symbol, target, target, target, index + 1, funding_rate=0.001))
                for event in exits:
                    ledger.append("FILL_OBSERVED", {"cycle_id": result["cycle_id"], "client_order_id": event.client_order_id,
                        "symbol": symbol, "side": "SELL" if position.side == "BUY" else "BUY", "quantity": position.quantity,
                        "price": event.price, "fee": venue.fills[-1].fee})
                    ledger.append("PROTECTION_TRIGGERED", {"cycle_id": result["cycle_id"], "symbol": symbol,
                        "client_order_id": event.client_order_id, "price": event.price})
                if symbol not in venue.positions:
                    trade = venue.closed_trades[-1]
                    ledger.append("TRADE_CLOSED", {"cycle_id": result["cycle_id"], "symbol": symbol,
                        "net_pnl": trade["net_pnl"], "gross_pnl": trade["gross_pnl"],
                        "entry_fee": trade["entry_fee"], "exit_fee": trade["exit_fee"], "funding": trade["funding"]})
            results.append(result)
    events = ledger.all()
    counts = Counter(event["event_type"] for event in events)
    rejection_codes = Counter(r.get("reason", "UNKNOWN") for r in results if r.get("status") in {"REJECTED", "PARKED", "SKIPPED"})
    anomalies = []
    if venue.positions:
        anomalies.append("OPEN_POSITIONS")
    if inject_integrity_failure:
        anomalies.append("INTEGRITY_FAILURE_INJECTED")
    integrity_ok = not anomalies and counts["CYCLE_TERMINAL"] == cycles * len(symbols)
    fees = sum(fill.fee for fill in venue.fills)
    net_pnl = sum(float(trade["net_pnl"]) for trade in venue.closed_trades)
    runtime_health = assess_runtime_health({"market_data": market_marks, "decisions": decision_statuses})
    report = {"run_id": uuid.uuid4().hex[:12], "mode": "paper", "status": "PASS" if integrity_ok else "FAIL",
              "integrity_ok": integrity_ok, "cycles_requested": cycles * len(symbols),
              "cycles_completed": len(results), "orders_placed": len(venue.orders), "signed_calls": 0,
              "network_calls": 0, "counts": {**counts, "cycles": len(results)},
              "rejection_codes": dict(rejection_codes), "degraded_states": [],
              "duplicate_prevention": {"ledger_claims": len(results), "duplicate_events": counts["CYCLE_TERMINAL"] - len(results)},
              "protection_reconciliation": {"verified": counts["PROTECTION_VERIFIED"], "reconciled": counts["POSITION_RECONCILED"]},
              "provider": {"name": "fake", "calls": len(results), "failures": 0, "latency_ms": 0},
              "open_positions": [p.__dict__ for p in venue.read_positions()],
              "closed_trades": venue.closed_trades, "fees": fees, "funding": venue.read_balance()["funding_paid"] - venue.read_balance()["funding_received"],
              "net_pnl": net_pnl, "runtime_health": runtime_health,
              "fee_inclusive_outcome": {"fees_paid": fees, "realized_pnl": net_pnl},
              "anomalies": anomalies, "ledger_events_before": events_before, "ledger_events_after": len(events)}
    write_run_report(report, reports_dir)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="bounded offline paper execution using FakeExchange only")
    parser.add_argument("--mode", choices=["paper"], required=True)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT"])
    parser.add_argument("--scenario", choices=["hold", "enter"], default="hold")
    parser.add_argument("--ledger", default="data/autonomous-paper.sqlite3")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--inject-integrity-failure", action="store_true")
    args = parser.parse_args()
    try:
        symbols = [symbol.strip().upper() for value in args.symbols for symbol in value.split(",") if symbol.strip()]
        report = run_paper(args.cycles, symbols,
                           Path(args.ledger), Path(args.reports_dir), args.scenario, args.inject_integrity_failure)
    except Exception as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))
    if not report["integrity_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
