"""TDD suite for the corpus acquisition + unified-quality-gate module.

These tests drive ``scripts/acquire_corpus``: a reusable, fail-closed path that
acquires a manifest of public-history datasets, refuses any dataset that fails
the unified data-quality gate (structural ``ok`` + wick-spike gate + coverage
gate), persists only validated datasets, and writes a corpus manifest.

RED: the module is imported at module load, so collection fails with ImportError
until ``scripts/acquire_corpus`` exists.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scripts.acquire_corpus import (
    acquire_corpus,
    CorpusAcquisitionError,
    CorpusResult,
    write_corpus_manifest,
)

from src.market.models import Candle
from src.market.history import HistoryDataset, data_quality_report, load_dataset


STEP_MS = 60_000  # 1m


def _normal_candles(n: int, start_ts: int, base: float = 100.0) -> list[Candle]:
    out: list[Candle] = []
    ts = start_ts
    price = base
    for _ in range(n):
        o = price
        c = price * 1.001
        h = max(o, c) * 1.002
        low = min(o, c) * 0.998
        out.append(Candle("1m", o, h, low, c, 10.0, ts))
        ts += STEP_MS
        price = c
    return out


def _wick_spike_candles(n: int, start_ts: int, base: float = 100.0) -> list[Candle]:
    out = _normal_candles(n, start_ts, base)
    # Replace the middle candle with a 100%-of-price upper wick (phantom wick).
    mid = len(out) // 2
    bad = out[mid]
    out[mid] = Candle("1m", bad.open, bad.close * 2.0, bad.low, bad.close, bad.volume, bad.source_ts_ms)
    return out


class _FakeClient:
    """Minimal stand-in for ``BitgetPublicClient`` driven by a per-symbol map."""

    product_type = "SUSDT-FUTURES"

    def __init__(self, data: dict[str, tuple[list[Candle], list[tuple[int, float]]]]):
        self._data = data
        self.fetch_calls = 0

    async def fetch_candles(self, symbol: str, granularity: str = "1m", limit: int = 100,
                            end_time_ms=None, allow_partial=True) -> list[Candle]:
        self.fetch_calls += 1
        candles, _ = self._data[symbol]
        return list(candles[-limit:])

    async def fetch_history_funding_rate(self, symbol: str, limit: int = 100,
                                         end_time_ms=None) -> list[tuple[int, float]]:
        _, funding = self._data[symbol]
        return list(funding)


def _spec(symbol: str, max_candles: int, end_time_ms: int) -> dict:
    return {"symbol": symbol, "granularity": "1m", "max_candles": max_candles,
            "end_time_ms": end_time_ms}


def _fetched_at(syms: dict[str, list[Candle]], step_ms: int = STEP_MS) -> int:
    # fetched_at must sit after the newest candle to avoid future-dated rejection.
    mx = max(c.source_ts_ms for cs in syms.values() for c in cs)
    return mx + step_ms * 2 + 1000


def _client_for(symbols_candles: dict[str, list[Candle]]) -> _FakeClient:
    data = {sym: (cs, []) for sym, cs in symbols_candles.items()}
    return _FakeClient(data)


def test_acquire_corpus_writes_datasets_and_manifest(tmp_path: Path):
    syms = {"AAAUSDT": _normal_candles(50, 1_000_000_000_000),
            "BBBUSDT": _normal_candles(50, 2_000_000_000_000)}
    client = _client_for(syms)
    specs = [_spec("AAAUSDT", 50, 1_000_000_050_000), _spec("BBBUSDT", 50, 2_000_000_050_000)]
    fetched_at = _fetched_at(syms)

    result = asyncio.run(
        acquire_corpus(client, specs, tmp_path, fetched_at_ms=fetched_at)
    )

    assert isinstance(result, CorpusResult)
    assert result.acquired == 2
    assert result.skipped == 0
    assert len(result.entries) == 2
    for entry in result.entries:
        p = Path(entry.path)
        assert p.exists()
        ds = load_dataset(p)
        assert isinstance(ds, HistoryDataset)
        assert ds.symbol == entry.symbol
        assert entry.candle_count == 50
        # Quality facts are captured in the manifest entry.
        assert entry.quality["ok"] is True

    manifest_path = write_corpus_manifest(tmp_path, result.entries)
    assert Path(manifest_path).exists()
    import json
    manifest = json.loads(Path(manifest_path).read_text())
    assert len(manifest["datasets"]) == 2


def test_acquire_corpus_fails_closed_on_wick_spike(tmp_path: Path):
    # One normal symbol and one with a phantom wick; the batch must refuse closed.
    syms = {
        "GOODUSDT": _normal_candles(50, 1_000_000_000_000),
        "BADUSDT": _wick_spike_candles(50, 2_000_000_000_000),
    }
    client = _client_for(syms)
    specs = [_spec("GOODUSDT", 50, 1_000_000_050_000), _spec("BADUSDT", 50, 2_000_000_050_000)]
    fetched_at = _fetched_at(syms)

    with pytest.raises(CorpusAcquisitionError) as exc:
        asyncio.run(acquire_corpus(client, specs, tmp_path, fetched_at_ms=fetched_at))

    # The bad dataset file must NOT be written, and no manifest is finalized.
    assert not (tmp_path / "BADUSDT_1m.json").exists()
    assert not (tmp_path / "corpus_manifest.json").exists()
    # The good dataset is individually valid but the corpus is not blessed.
    assert "BADUSDT" in str(exc.value) or "wick" in str(exc.value).lower()


def test_acquire_corpus_refuses_overwrite_without_force(tmp_path: Path):
    syms = {"REUSEUSDT": _normal_candles(40, 3_000_000_000_000)}
    specs = [_spec("REUSEUSDT", 40, 3_000_000_040_000)]
    fetched_at = _fetched_at(syms)

    client = _client_for(syms)
    asyncio.run(acquire_corpus(client, specs, tmp_path, fetched_at_ms=fetched_at))
    assert client.fetch_calls == 1

    # Re-run without force: existing good dataset is reused, no new fetch.
    client2 = _client_for(syms)
    res = asyncio.run(acquire_corpus(client2, specs, tmp_path, fetched_at_ms=fetched_at))
    assert res.skipped == 1
    assert res.acquired == 0
    assert client2.fetch_calls == 0

    # Re-run with force: re-fetches and overwrites.
    client3 = _client_for(syms)
    res = asyncio.run(acquire_corpus(client3, specs, tmp_path, fetched_at_ms=fetched_at, force=True))
    assert res.acquired == 1
    assert client3.fetch_calls == 1


class _FlakyClient:
    """Fake client that raises a network error for one designated symbol."""

    product_type = "SUSDT-FUTURES"

    def __init__(self, data, fail_symbol):
        self._data = data
        self._fail = fail_symbol

    async def fetch_candles(self, symbol, granularity="1m", limit=100,
                            end_time_ms=None, allow_partial=True):
        if symbol == self._fail:
            from src.market.bitget_public import PublicMarketError
            raise PublicMarketError("PUBLIC_HTTP_400")
        return list(self._data[symbol][-limit:])

    async def fetch_history_funding_rate(self, symbol, limit=100, end_time_ms=None):
        if symbol == self._fail:
            from src.market.bitget_public import PublicMarketError
            raise PublicMarketError("PUBLIC_HTTP_400")
        return []


def test_acquire_corpus_tolerant_skips_network_errors(tmp_path: Path):
    from scripts.acquire_corpus import acquire_corpus_tolerant

    syms = {"GOODUSDT": _normal_candles(40, 3_000_000_000_000),
            "BADNETUSDT": _normal_candles(40, 4_000_000_000_000)}
    specs = [_spec("GOODUSDT", 40, 3_000_000_040_000), _spec("BADNETUSDT", 40, 4_000_000_040_000)]
    fetched_at = _fetched_at(syms)
    client = _FlakyClient(syms, "BADNETUSDT")

    entries, rejected = acquire_corpus_tolerant(client, specs, tmp_path, fetched_at_ms=fetched_at)

    # The good symbol is acquired; the network-failing symbol is skipped, not fatal.
    assert len(entries) == 1
    assert entries[0].symbol == "GOODUSDT"
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "BADNETUSDT"
    assert rejected[0]["reason"] == "network"
    assert (tmp_path / "GOODUSDT_1m.json").exists()
    assert not (tmp_path / "BADNETUSDT_1m.json").exists()
