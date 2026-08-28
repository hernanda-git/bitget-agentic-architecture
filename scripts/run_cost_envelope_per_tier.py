"""Offline per-liquidity-tier cost-stress envelope runner.

Replays the existing public historical corpus (``data/history/*.json``) through
``cost_envelope_per_tier`` using the OBSERVED per-symbol spread loaded from the
committed Phase 36 calibration table, producing reproducible, committed
evidence that the cost-stress envelope is evaluated per liquidity tier rather
than under one global assumed half-spread.

It is network-free and always keeps the Phase 6 promotion gate blocked:
``selection_blocked`` / ``promotion_blocked`` are forced ``True`` by
``cost_envelope_per_tier`` and no winner / promoted / selected / go_live /
positive_edge key is ever emitted. No orders, signed calls, positions, or
realized PnL are produced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_per_tier_report(history_dir, table_path, *,
                          limit: int = 300,
                          fee_mults: Sequence[float] = (1.0, 2.0),
                          funding_mults: Sequence[float] = (1.0, 2.0),
                          slippage_mults: Sequence[float] = (1.0, 2.0)) -> dict:
    """Replay every historical symbol with an observed spread through the
    per-tier cost-stress envelope.

    Only symbols present in the observed-spread ``table`` are recalibrated and
    replayed; the rest are reported under ``unknown_symbols`` and never priced
    as cheap. Fully offline (local history + committed table).
    """
    from src.evaluation.baseline import BaselineConfig
    from src.evaluation.cost_sensitivity import cost_envelope_per_tier
    from src.evaluation.symbol_cost_table import load_observed_spread_table
    from src.market.history import load_dataset, snapshots_from_dataset

    history_dir = Path(history_dir)
    table = load_observed_spread_table(Path(table_path))

    sym_snaps: list[tuple[str, tuple]] = []
    skipped: list[str] = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            ds = load_dataset(path)
        except Exception:
            # skip any non-dataset json (manifest, etc.)
            continue
        symbol = ds.symbol
        try:
            snaps = snapshots_from_dataset(ds)[:limit]
        except Exception:
            # unparseable symbol/geometry for this dataset; skip, don't crash
            skipped.append(symbol)
            continue
        if not snaps:
            continue
        # Every loaded symbol is passed through. ``cost_envelope_per_tier``
        # recalibrates only those present in the observed-spread table and
        # reports the rest under ``unknown_symbols`` (never priced as cheap).
        sym_snaps.append((symbol, snaps))

    result = cost_envelope_per_tier(
        sym_snaps, table, BaselineConfig(real_funding=False),
        fee_mults=tuple(fee_mults), funding_mults=tuple(funding_mults),
        slippage_mults=tuple(slippage_mults))
    result["history_dir"] = str(history_dir)
    result["table_path"] = str(table_path)
    result["n_snapshots_per_symbol"] = limit
    result["n_symbols_replayed"] = len(sym_snaps)
    result["skipped_symbols"] = skipped
    return result


def _summarize_md(res: dict, table_path: str) -> str:
    lines = [
        "# Per-liquidity-tier cost-stress envelope (observed spread)",
        "",
        f"Table: `{table_path}`",
        f"Symbols replayed: {res.get('n_symbols_replayed', 0)} | "
        f"Snapshots/symbol: {res.get('n_snapshots_per_symbol')}",
        f"Unknown (no observed spread): {res.get('unknown_symbols', [])}",
        "",
        f"- selection_blocked: {res['selection_blocked']}",
        f"- promotion_blocked: {res['promotion_blocked']}",
        "",
        "## Tiers",
        "",
        "| Tier | Symbols | n_cells | min_net | median_net | max_net | any_profitable | all_blocked |",
        "|------|---------|---------|---------|------------|---------|----------------|-------------|",
    ]
    for tier, t in sorted(res["tiers"].items()):
        lines.append(
            f"| {tier} | {', '.join(t['symbols']) or '-'} | {t['n_cells']} | "
            f"{t['min_net']:.4f} | {t['median_net']:.4f} | {t['max_net']:.4f} | "
            f"{t['any_profitable']} | {t['all_blocked']} |")
    lines.append("")
    lines.append("**Honest reading:** every tier here is reported under the "
                 "blocked gate. The table calibrates the *minimum* quoted "
                 "spread; actual fills at size are worse. No promotion is "
                 "authorized while the deterministic baseline is negative.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history-dir", default="data/history",
                    help="directory of HistoryDataset JSON files")
    ap.add_argument("--table", default="reports/phase-36/orderbook_calibration.json",
                    help="Phase 36 observed-spread calibration JSON")
    ap.add_argument("--limit", type=int, default=300,
                    help="max snapshots per symbol")
    ap.add_argument("--out-json", default="reports/phase-37/per_tier_cost_envelope.json",
                    help="output JSON path")
    ap.add_argument("--out-md", default="reports/phase-37/per_tier_cost_envelope.md",
                    help="output markdown summary path")
    args = ap.parse_args(argv)

    res = build_per_tier_report(args.history_dir, args.table, limit=args.limit)
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(res, indent=2, default=str))
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_summarize_md(res, args.table))
    print(f"replayed {res.get('n_symbols_replayed', 0)} symbols; "
          f"selection_blocked={res['selection_blocked']}; "
          f"promotion_blocked={res['promotion_blocked']}")
    print(f"wrote {out_json} and {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
