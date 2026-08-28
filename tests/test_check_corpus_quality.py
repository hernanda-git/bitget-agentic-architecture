"""Corpus data-quality scan (TDD, offline, fail-closed).

The historical corpus in ``data/history/*.json`` is the ground truth for every
cost-stress / walk-forward / replay result in this repo. A malformed,
tampered, or non-conforming dataset must be *surfaced*, never silently skipped
or laundered into a clean run. This suite covers ``scripts/check_corpus_quality``:
it loads every dataset, validates symbol format, integrity hash, spread, and
candle non-emptiness, and reports problems fail-closed (``ok=False`` and a
non-zero exit when any defect is found).

Tests first (RED): the module and ``scan_corpus`` do not exist yet.
"""
from __future__ import annotations
from pathlib import Path

import json


def _dataset_dict(symbol: str, *, tamper: bool = False, candles: int = 10):
    from src.market.history import HistoryDataset
    from src.market.models import Candle

    ts = 1_700_000_000_000
    cs = []
    for i in range(candles):
        m = 100.0 + i
        cs.append(Candle("1m", m * 0.999, m * 1.001, m * 0.998, m, 10.0, ts + i * 60_000))
    ds = HistoryDataset(symbol=symbol, product_type="SUSDT-FUTURES", granularity="1m",
                        fetched_at_ms=ts, candles=tuple(cs), funding=(),
                        assumed_half_spread_bps=1.0)
    d = ds.to_dict()
    if tamper:
        # break integrity without updating the hash
        d["candles"][0][1] = d["candles"][0][1] + 1.0
    return d


def test_checker_module_exists():
    """RED anchor: the checker module + scan_corpus must exist."""
    import scripts.check_corpus_quality as m
    assert hasattr(m, "scan_corpus")
    assert hasattr(m, "main")


def test_scan_corpus_flags_defects(tmp_path):
    from scripts.check_corpus_quality import scan_corpus

    hist = tmp_path / "hist"
    hist.mkdir()
    # valid dataset
    (hist / "BTCUSDT_1m.json").write_text(json.dumps(_dataset_dict("BTCUSDT")))
    # invalid symbol (the real TINY_1m.json defect class)
    (hist / "TINY_1m.json").write_text(json.dumps(_dataset_dict("TINY")))
    # integrity hash mismatch (tampered candles)
    (hist / "BROKEN_1m.json").write_text(json.dumps(_dataset_dict("ETHUSDT", tamper=True)))
    # malformed json
    (hist / "GARBAGE_1m.json").write_text("{ not valid json")
    # manifest-like file (no symbol) should be ignored, not a defect
    (hist / "corpus_manifest.json").write_text(json.dumps({"symbols": ["BTCUSDT"]}))

    res = scan_corpus(hist)

    assert res["ok"] is False
    assert res["n_problems"] == 3  # TINY, BROKEN, GARBAGE
    assert "BTCUSDT_1m.json" not in res["problems"]
    assert "TINY_1m.json" in res["problems"]
    assert "BROKEN_1m.json" in res["problems"]
    assert "GARBAGE_1m.json" in res["problems"]
    assert "corpus_manifest.json" not in res["problems"]
    # each problem carries a status + issues
    tiny = res["files"]["TINY_1m.json"]
    assert tiny["status"] == "invalid_symbol"
    broken = res["files"]["BROKEN_1m.json"]
    assert broken["status"] == "integrity_failed"


def test_scan_corpus_clean_dir_ok(tmp_path):
    from scripts.check_corpus_quality import scan_corpus

    hist = tmp_path / "hist"
    hist.mkdir()
    (hist / "BTCUSDT_1m.json").write_text(json.dumps(_dataset_dict("BTCUSDT")))
    (hist / "ETHUSDT_1m.json").write_text(json.dumps(_dataset_dict("ETHUSDT", candles=50)))
    res = scan_corpus(hist)
    assert res["ok"] is True
    assert res["n_problems"] == 0
    assert res["files"]["BTCUSDT_1m.json"]["status"] == "ok"
