"""Public historical dataset acquisition and real-data evaluation (no signed calls)."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from src.market.bitget_public import BitgetPublicClient, PublicMarketError
from src.market.models import Candle

ROOT = Path(__file__).resolve().parents[1]


def candle_row(ts, o, h, l, c, v):
    return [str(ts), str(o), str(h), str(l), str(c), str(v)]


def make_client(universe):
    """Mock transport honoring endTime/limit like the real Bitget candle API."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if request.url.path.endswith("history-fund-rate"):
            return httpx.Response(200, json={"code": "00000", "data": []})
        end = int(params.get("endTime", "999999999999999"))
        limit = int(params.get("limit", "100"))
        rows = [r for r in universe if int(r[0]) <= end]
        rows = rows[-limit:] if rows else []
        return httpx.Response(200, json={"code": "00000", "data": rows})

    client = BitgetPublicClient(venue="bitget", product_type="SUSDT-FUTURES",
                                transport=httpx.MockTransport(handler), min_interval_seconds=0)
    client.calls = calls
    return client


def test_demo_product_accepted_and_live_product_rejected():
    """Boundary: only SUSDT-FUTURES (demo) is allowed; USDT-FUTURES is the live product."""
    client = BitgetPublicClient(venue="bitget", product_type="SUSDT-FUTURES")
    assert client.product_type == "SUSDT-FUTURES"
    with pytest.raises(ValueError):
        BitgetPublicClient(venue="bitget", product_type="USDT-FUTURES")


def test_fetch_history_funding_rate_normalizes_to_chronological_records():
    seen_params = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("history-fund-rate"):
            seen_params.append(dict(request.url.params))
            return httpx.Response(200, json={"code": "00000", "data": [
                {"symbol": "BTCUSDT", "fundingRate": "0.000018", "fundingTime": "1787702400000"},
                {"symbol": "BTCUSDT", "fundingRate": "0.000100", "fundingTime": "1787644800000"},
            ]})
        return httpx.Response(404, json={})

    client = BitgetPublicClient(venue="bitget", product_type="SUSDT-FUTURES",
                                transport=httpx.MockTransport(handler), min_interval_seconds=0)
    records = asyncio.run(client.fetch_history_funding_rate("BTCUSDT", limit=100))
    assert records == [(1787644800000, 0.0001), (1787702400000, 0.000018)]
    assert seen_params[0]["limit"] == "100"


def test_candle_history_paginates_backward_dedupes_and_stops_on_empty_page():
    from src.market.history import fetch_candle_history

    universe = [
        candle_row(60000, 99, 100, 98, 99.5, 4),
        candle_row(120000, 100, 101, 99, 100.5, 5),
        candle_row(180000, 100.5, 102, 100, 101, 6),
    ]
    client = make_client(universe)
    candles = asyncio.run(fetch_candle_history(client, "BTCUSDT", "1m",
                                               end_time_ms=180000, max_candles=10, page_size=2))
    assert [c.source_ts_ms for c in candles] == [60000, 120000, 180000]
    assert len(client.calls) >= 2


def test_candle_history_stops_at_max_candles():
    from src.market.history import fetch_candle_history

    universe = [candle_row(ts, 100, 101, 99, 100.5, 5) for ts in range(0, 9 * 60_000, 60_000)]
    client = make_client(universe)
    candles = asyncio.run(fetch_candle_history(client, "BTCUSDT", "1m",
                                               end_time_ms=9 * 60_000 - 1, max_candles=4))
    assert len(candles) == 4
    assert [c.source_ts_ms for c in candles] == sorted(c.source_ts_ms for c in candles)


def test_fetch_candles_passes_end_time_and_allows_partial_page():
    client = make_client([
        candle_row(1787722980000, 79059.9, 79096, 79055.2, 79063.5, 7.6),
        candle_row(1787723040000, 79063.5, 79081.5, 79043, 79076.4, 5.19),
    ])
    candles = asyncio.run(client.fetch_candles("BTCUSDT", "1m", 5, end_time_ms=1787723040000, allow_partial=True))
    assert client.calls[0]["endTime"] == "1787723040000"
    assert [c.source_ts_ms for c in candles] == [1787722980000, 1787723040000]
    assert candles[-1].close == 79076.4


def test_fetch_candles_without_allow_partial_rejects_short_page():
    client = make_client([candle_row(1787722980000, 79059.9, 79096, 79055.2, 79063.5, 7.6)])
    with pytest.raises(PublicMarketError, match="CANDLE_INCOMPLETE_WINDOW"):
        asyncio.run(client.fetch_candles("BTCUSDT", "1m", 5))

from src.market.history import HistoryDataset, FundingRecord, snapshots_from_dataset, acquire_dataset


def _sample_dataset() -> HistoryDataset:
    candles = tuple(Candle("1m", 100 + i, 101 + i, 99 + i, 100.5 + i, 5, 1_000 + i * 60_000)
                    for i in range(40))
    funding = (FundingRecord(1_000, 0.0001), FundingRecord(2_000, 0.0002))
    return HistoryDataset(symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
                          fetched_at_ms=9_999, candles=candles, funding=funding,
                          assumed_half_spread_bps=0.5)


def test_dataset_round_trips_through_json_and_validates_integrity():
    dataset = _sample_dataset()
    payload = json.dumps(dataset.to_dict(), sort_keys=True)
    restored = HistoryDataset.from_dict(json.loads(payload))
    assert restored == dataset
    assert restored.integrity_hash() == dataset.integrity_hash()


def test_dataset_detects_tampering_on_load():
    dataset = _sample_dataset()
    payload = dataset.to_dict()
    payload["candles"][0][5] = payload["candles"][0][5] + 1.0  # mutate volume
    with pytest.raises(ValueError, match="integrity"):
        HistoryDataset.from_dict(payload)


def test_snapshots_from_dataset_pass_replay_validation_and_only_attach_funding_on_settlement_bars():
    from src.evaluation.baseline import _validate_replay_snapshots
    base = 1_000_000
    candles = tuple(Candle("1m", 100 + i, 101 + i, 99 + i, 100.5 + i, 5, base + i * 60_000)
                    for i in range(20))
    funding = (FundingRecord(base + 5 * 60_000, 0.0001), FundingRecord(base + 15 * 60_000, 0.0002))
    dataset = HistoryDataset("BTCUSDT", "SUSDT-FUTURES", "1m", 9_999, candles, funding, 0.5)
    snapshots = snapshots_from_dataset(dataset, window=5)
    assert len(snapshots) == len(candles)
    assert all(s.snapshot_hash == s.computed_hash() for s in snapshots)
    assert all(s.bid <= s.ask for s in snapshots)
    # Funding is charged only on the settlement bars, not on every bar.
    assert snapshots[5].funding_rate == 0.0001
    assert snapshots[15].funding_rate == 0.0002
    assert all(s.funding_rate is None for i, s in enumerate(snapshots) if i not in (5, 15))
    _validate_replay_snapshots(snapshots)  # must not raise


def test_acquire_dataset_wires_pagination_and_funding(monkeypatch):
    universe = [candle_row(ts, 100, 101, 99, 100.5, 5) for ts in range(0, 12 * 60_000, 60_000)]
    client = make_client(universe)
    dataset = asyncio.run(acquire_dataset(client, "BTCUSDT", "1m", end_time_ms=11 * 60_000,
                                           max_candles=10, funding_limit=5))
    assert len(dataset.candles) == 10
    assert dataset.product_type == "SUSDT-FUTURES"


def test_evaluate_real_history_on_stored_dataset(tmp_path, monkeypatch):
    import importlib.util
    from src.market.history import HistoryDataset, FundingRecord, snapshots_from_dataset, acquire_dataset
    # store a dataset
    dataset = _sample_dataset()
    store = tmp_path / "ds.json"
    store.write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True))
    out = tmp_path / "out.json"
    spec = importlib.util.spec_from_file_location("eval_real", ROOT / "scripts" / "evaluate_real_history.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr("sys.argv", ["evaluate_real_history.py", "--dataset", str(store), "--output", str(out)])
    rc = mod.main()
    assert rc == 0
    result = json.loads(out.read_text())
    assert result["baseline"]["closed_trades"] >= 0
    assert result["walk_forward"]


def test_real_funding_flag_uses_settlement_rates_not_proxy():
    from src.evaluation.baseline import run_baseline, BaselineConfig
    base = 1_000_000
    candles = tuple(Candle("1m", 100 + i, 101 + i, 99 + i, 100.5 + i, 5, base + i * 60_000)
                    for i in range(40))
    funding = (FundingRecord(base + 10 * 60_000, 0.0001),)
    dataset = HistoryDataset("BTCUSDT", "SUSDT-FUTURES", "1m", 9_999, candles, funding, 0.5)
    snaps = snapshots_from_dataset(dataset, window=5)
    proxy = run_baseline(snaps, BaselineConfig(real_funding=False))
    real = run_baseline(snaps, BaselineConfig(real_funding=True))
    # Proxy path scales by funding_bps (2bps => 0.0002/event); real path uses the
    # single 0.0001 settlement rate, so real funding must be far smaller.
    assert real.funding < proxy.funding
