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


# ---------------------------------------------------------------------------
# Data-quality reporting for historical datasets (Phase 5 research hardening)
# ---------------------------------------------------------------------------

def _mk_candle(ts, close=100.0, open_=99.5, high=101.0, low=99.0, volume=5.0):
    return Candle("1m", open_, high, low, close, volume, ts)


def _mk_dataset(candles, funding=()):
    from src.market.history import HistoryDataset, FundingRecord
    return HistoryDataset(
        symbol="BTCUSDT", product_type="SUSDT-FUTURES", granularity="1m",
        fetched_at_ms=max(c.source_ts_ms for c in candles),
        candles=tuple(candles),
        funding=tuple(FundingRecord(ft, rate) for ft, rate in funding),
        assumed_half_spread_bps=0.5,
    )


def test_expected_interval_ms_parses_supported_granularities():
    from src.market.history import expected_interval_ms

    assert expected_interval_ms("1m") == 60_000
    assert expected_interval_ms("5m") == 300_000
    assert expected_interval_ms("15m") == 900_000
    assert expected_interval_ms("1h") == 3_600_000
    assert expected_interval_ms("4h") == 14_400_000
    assert expected_interval_ms("1d") == 86_400_000
    with pytest.raises(ValueError):
        expected_interval_ms("7x")


def test_data_quality_report_is_ok_on_clean_contiguous_dataset():
    from src.market.history import data_quality_report

    candles = [_mk_candle(60_000 * i) for i in range(1, 11)]
    report = data_quality_report(_mk_dataset(candles))
    assert report.candle_count == 10
    assert report.duplicate_timestamps == 0
    assert report.non_chronological == 0
    assert report.gaps == ()
    assert report.ok is True


def test_data_quality_report_flags_duplicate_and_regressing_timestamps():
    from src.market.history import data_quality_report

    candles = [_mk_candle(60_000), _mk_candle(120_000), _mk_candle(120_000), _mk_candle(90_000)]
    report = data_quality_report(_mk_dataset(candles))
    assert report.duplicate_timestamps == 1
    assert report.non_chronological == 1
    assert report.ok is False


def test_data_quality_report_reports_missing_bar_gaps():
    from src.market.history import data_quality_report

    # 1m bars with a 4-minute hole between 120000 and 360000 (two missing bars).
    candles = [_mk_candle(60_000), _mk_candle(120_000), _mk_candle(360_000), _mk_candle(420_000)]
    report = data_quality_report(_mk_dataset(candles))
    assert len(report.gaps) == 1
    gap = report.gaps[0]
    assert gap["start_ms"] == 120_000
    assert gap["end_ms"] == 360_000
    assert gap["missing_bars"] == 3  # 240000ms / 60000ms - 1
    assert report.max_missing_bars == 3


def test_data_quality_report_counts_zero_volume_bars():
    from src.market.history import data_quality_report

    candles = [_mk_candle(60_000, volume=5.0), _mk_candle(120_000, volume=0.0), _mk_candle(180_000, volume=1.0)]
    report = data_quality_report(_mk_dataset(candles))
    assert report.zero_volume_bars == 1


def test_data_quality_report_compares_funding_coverage_to_eight_hour_cadence():
    from src.market.history import data_quality_report

    # ~25h span: first bar at 00:00 UTC day 1, last bar at 01:00 UTC day 2.
    start = 1_787_616_000_000  # arbitrary aligned epoch minute
    candles = [_mk_candle(start + i * 60_000) for i in range(25 * 60)]
    # Two settlements recorded inside the span -> one 8h slot uncovered.
    funding = [(start + 8 * 3_600_000, 0.0001), (start + 16 * 3_600_000, 0.0002)]
    report = data_quality_report(_mk_dataset(candles, funding=funding))
    span_ms = candles[-1].source_ts_ms - candles[0].source_ts_ms
    assert report.funding_expected_settlements == span_ms // (8 * 3_600_000)  # 3
    assert report.funding_records_in_range == 2
    assert report.funding_missing == 1


# ---------------------------------------------------------------------------
# Evaluator CLI wiring: data-quality gate and payload embedding
# ---------------------------------------------------------------------------

def _write_dataset(path, candles):
    from src.market.history import HistoryDataset
    dataset = _mk_dataset(candles)
    path.write_text(json.dumps(dataset.to_dict(), indent=2, sort_keys=True) + "\n")
    return path


def test_evaluator_cli_embeds_data_quality_and_passes_clean_dataset(tmp_path):
    import subprocess
    import sys

    dataset_path = _write_dataset(
        tmp_path / "clean.json", [_mk_candle(60_000 * i) for i in range(1, 41)])
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(output_path.read_text())
    assert payload["data_quality"]["ok"] is True
    assert payload["data_quality"]["candle_count"] == 40


def test_evaluator_cli_fails_closed_on_structurally_bad_dataset(tmp_path):
    import subprocess
    import sys

    candles = [_mk_candle(60_000), _mk_candle(120_000), _mk_candle(120_000)]
    dataset_path = _write_dataset(tmp_path / "dupes.json", candles)
    output_path = tmp_path / "out.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_real_history.py"),
         "--dataset", str(dataset_path), "--output", str(output_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "duplicate_timestamps=1" in (proc.stdout + proc.stderr)
    assert not output_path.exists()


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
