import asyncio
import math
from dataclasses import replace

import pytest

from src.agent.context import PortfolioView
from src.agentic_engine import Action, AgentDecision, Policy
from src.config import ConfigError, from_mapping
from src.execution.fake_exchange import FakeExchange
from src.ledger.sqlite import EventLedger
from src.market.models import Candle, MarketSnapshot
from src.policy.semantic import SemanticPolicy, SemanticState, validate_semantic
from src.policy.sizing import SizingError, size_for_risk
from src.providers.fake import FakeProvider
from src.providers.ports import ProviderResponse
from src.risk.exposure import ExposureLimits, check_exposure
from src.risk.portfolio import PortfolioSnapshot, PositionSnapshot
from src.runtime.paper_runtime import AutonomousPaperRuntime


def test_portfolio_snapshot_tracks_notional_pnl_costs_peak_and_drawdown():
    snapshot = PortfolioSnapshot.from_positions(
        equity=950.0, available_margin=700.0, used_margin=250.0,
        positions=[PositionSnapshot("BTCUSDT", "BUY", 2.0, 100.0, 105.0, 1.0),
                   PositionSnapshot("ETHUSDT", "SELL", 3.0, 50.0, 45.0, 2.0)],
        realized_daily_pnl=-30.0, fees_today=4.0, funding_today=1.0,
        peak_equity=1000.0,
    )
    assert snapshot.gross_notional == 345.0
    assert snapshot.net_notional == 75.0
    assert snapshot.long_notional == 210.0
    assert snapshot.short_notional == 135.0
    assert snapshot.unrealized_pnl == 3.0
    assert snapshot.drawdown == 50.0
    assert snapshot.positions_by_symbol["BTCUSDT"].quantity == 2.0


def test_portfolio_snapshot_round_trips_across_ledger_restart(tmp_path):
    path = tmp_path / "portfolio.sqlite3"
    ledger = EventLedger(path)
    value = PortfolioSnapshot(equity=900, available_margin=600, used_margin=300,
                              gross_notional=500, net_notional=100, long_notional=300,
                              short_notional=200, positions_by_symbol={}, realized_daily_pnl=-50,
                              unrealized_pnl=0, fees_today=3, funding_today=2,
                              peak_equity=1000, drawdown=100)
    ledger.save_portfolio_snapshot(value)
    restored = EventLedger(path).latest_portfolio_snapshot()
    assert restored == value


def test_executable_limits_reject_missing_or_infinite_values():
    with pytest.raises(ConfigError):
        from_mapping({"policy": {"max_daily_loss_usd": 2}})
    with pytest.raises(ConfigError):
        from_mapping({"policy": {
            "max_daily_loss_usd": 2, "max_drawdown_pct": math.inf,
            "max_position_notional_usd": 10, "max_total_notional_usd": 20,
            "max_concurrent_positions": 2, "max_leverage": 2,
            "max_orders_per_minute": 2,
        }})


def test_sizing_accounts_for_multiplier_equity_and_existing_exposure():
    result = size_for_risk(side="BUY", entry=100, stop_loss=95, requested_risk_usd=100,
                           min_notional_usd=10, max_notional_usd=1000, quantity_step=0.1,
                           contract_multiplier=2, available_equity_usd=300,
                           existing_gross_notional_usd=400, max_total_notional_usd=500)
    assert result.quantity == 0.5
    assert result.notional_usd == 100.0
    assert result.effective_risk_usd == 5.0


def test_exposure_gates_cover_gross_net_correlated_and_symbol_concentration():
    limits = ExposureLimits(max_gross_notional=100, max_net_notional=60,
                            max_correlated_notional=80, max_symbol_notional=50,
                            correlations={"BTCUSDT": {"ETHUSDT": 0.9}})
    positions = [PositionSnapshot("BTCUSDT", "BUY", 0.4, 100, 100, 0)]
    assert check_exposure("ETHUSDT", "BUY", 40, positions, limits).allowed is False
    assert check_exposure("BTCUSDT", "BUY", 10, positions, limits).code == "SYMBOL_CONCENTRATION_LIMIT"


def test_provider_quantity_is_ignored_and_runtime_uses_deterministic_sizing(tmp_path):
    response = ProviderResponse("OK", '{"decision_id":"decision-1234","action":"ENTER","symbol":"BTCUSDT","side":"BUY","entry":100,"stop_loss":95,"take_profit":110,"leverage":1,"max_notional_usd":20,"valid_until_ms":20000,"thesis":"t","invalidation":"i"}')
    snapshot = MarketSnapshot("BTCUSDT", 100, 99.9, 100.1, 0, 10, 10000, 10000,
                             (Candle("1m", 99, 101, 98, 100, 10, 10000),)).with_hash()
    policy = Policy(frozenset({"BTCUSDT"}), 3, 25, 20, 3, kill_switch=False,
                     requested_risk_usd=5, quantity_step=0.1, min_notional_usd=1,
                     max_total_notional_usd=25, available_equity_usd=1000)
    exchange = FakeExchange()
    result = asyncio.run(AutonomousPaperRuntime(FakeProvider([response]), policy,
        EventLedger(tmp_path / "e.db"), exchange).process(snapshot, PortfolioView(), 10500))
    assert result["status"] == "EXECUTED"
    assert exchange.fills[0].quantity == 0.2


def test_sizing_bypass_is_not_an_accepted_order_path():
    # A provider-chosen value is intentionally absurd and must never be passed through.
    with pytest.raises(SizingError):
        size_for_risk(side="BUY", entry=100, stop_loss=95, requested_risk_usd=5,
                      min_notional_usd=1, max_notional_usd=25, quantity_step=0.1,
                      provider_quantity=999999)
