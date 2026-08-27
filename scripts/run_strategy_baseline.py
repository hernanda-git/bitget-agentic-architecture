#!/usr/bin/env python3
"""Run the offline Phase 5 deterministic baseline. No network or signed calls."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.evaluation.baseline import BaselineConfig, run_baseline, run_walk_forward, run_cost_stress
from src.evaluation.stress import run_stress_matrix
from src.evaluation.statistics import compute_statistics
from src.evaluation.report_honesty import assert_truthful, assert_no_suspect_constant_series
from src.market.models import Candle, MarketSnapshot

def make_series(count: int = 36):
    out = []
    start = 1_700_000_000_000
    for i in range(count):
        closes = [100 + j * 0.5 for j in range(max(8, i + 1))]
        if i >= 18: closes = [c - (i - 17) * 3 for c in closes]
        candles = tuple(Candle("1m", c - .5, c + 1, c - 1, c, 10, start + j * 60_000) for j, c in enumerate(closes))
        ts = start + (len(closes) - 1) * 60_000
        out.append(MarketSnapshot("BTCUSDT", closes[-1], closes[-1] - .01, closes[-1] + .01, .0002, 100, ts, ts, candles=candles).with_hash())
    return tuple(out)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("reports/phase-5/baseline.json"))
    args = parser.parse_args()
    series = make_series()
    result = run_baseline(series)
    payload = dict(result.__dict__)
    payload["walk_forward_evaluation"] = run_walk_forward(series)
    payload["cost_stress"] = run_cost_stress(series)
    payload["stress_matrix"] = run_stress_matrix(series)
    payload["statistics"] = compute_statistics(result.trade_pnls)
    # Fail-closed honesty anchor: the deterministic gate is NEGATIVE_NET_PNL and
    # selection is always blocked, so every emitted report must carry that fact
    # and must never contain a promotion/winner/positive-verdict overclaim.
    payload["selection_blocked"] = True
    payload["report_honest"] = True
    assert_truthful(payload)  # raises ReportHonestyError on any overclaim
    # Flat-line layer: a derived metric that never varies is worse than no
    # metric (it launders silence as a result). The honest baseline must not
    # embed a dead constant series presented as a live signal.
    assert_no_suspect_constant_series(payload)  # raises ReportHonestyError on flat-line
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=lambda x: list(x) if isinstance(x, tuple) else x) + "\n")
    print(json.dumps(payload, sort_keys=True, default=lambda x: list(x) if isinstance(x, tuple) else x))
    return 0

if __name__ == "__main__": raise SystemExit(main())
