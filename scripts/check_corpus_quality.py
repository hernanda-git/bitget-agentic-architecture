"""Offline corpus data-quality scanner (fail-closed, network-free).

Every cost-stress / walk-forward / replay result in this repo rests on the
historical datasets in ``data/history/*.json``. This scanner loads each one,
validates symbol format, integrity hash, assumed spread, and candle
non-emptiness, and reports defects fail-closed: ``ok=False`` and a non-zero
process exit when any defect is found, so a dirty corpus can never be laundered
into a clean run. No network egress, no signing, no credentials.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Bitget USDT-margined perpetual symbols are upper-case and USDT-suffixed.
VALID_SYMBOL = re.compile(r"^[A-Z0-9]+USDT$")
# The corpus manifest is not a dataset; ignore it rather than flag it.
MANIFEST_NAMES = {"corpus_manifest.json"}


def _classify(path: Path, per: dict) -> bool:
    """Classify one history json file. Returns True if it is a defect."""
    name = path.name
    rec = {"path": name, "status": "ok", "issues": []}
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        rec["status"] = "malformed_json"
        rec["issues"].append(f"json parse error: {str(e)[:120]}")
        per[name] = rec
        return True
    if name in MANIFEST_NAMES or not isinstance(data, dict) or "symbol" not in data:
        rec["status"] = "ignored_non_dataset"
        per[name] = rec
        return False
    from src.market.history import load_dataset
    try:
        ds = load_dataset(path)
    except Exception as e:
        rec["status"] = "integrity_failed"
        rec["issues"].append(f"load/integrity error: {str(e)[:120]}")
        per[name] = rec
        return True
    sym = ds.symbol
    if not VALID_SYMBOL.match(sym):
        rec["status"] = "invalid_symbol"
        rec["issues"].append(f"symbol {sym!r} is not upper-case USDT-suffixed")
        per[name] = rec
        return True
    if not (isinstance(ds.assumed_half_spread_bps, (int, float))
            and ds.assumed_half_spread_bps > 0):
        rec["status"] = "bad_assumed_spread"
        rec["issues"].append(f"assumed_half_spread_bps={ds.assumed_half_spread_bps!r}")
        per[name] = rec
        return True
    if not ds.candles:
        rec["status"] = "empty_candles"
        rec["issues"].append("dataset has zero candles")
        per[name] = rec
        return True
    rec["n_candles"] = len(ds.candles)
    rec["symbol"] = sym
    per[name] = rec
    return False


def scan_corpus(history_dir) -> dict:
    """Scan every ``*.json`` in ``history_dir`` and report data-quality status.

    Returns a dict with ``ok`` (True iff no defects), ``n_files``,
    ``n_problems``, ``problems`` (list of filenames), and ``files`` (per-file
    status records). Manifest / non-dataset files are ignored, not flagged.
    """
    history_dir = Path(history_dir)
    per: dict[str, dict] = {}
    problems: list[str] = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            is_defect = _classify(path, per)
        except Exception as e:  # never crash the scan on one bad file
            per[path.name] = {"path": path.name, "status": "scan_error",
                              "issues": [str(e)[:120]]}
            problems.append(path.name)
            continue
        if is_defect:
            problems.append(path.name)
    n_files = len(per)
    return {
        "history_dir": str(history_dir),
        "n_files": n_files,
        "n_problems": len(problems),
        "ok": len(problems) == 0,
        "problems": sorted(problems),
        "files": per,
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history-dir", default="data/history",
                    help="directory of HistoryDataset JSON files")
    ap.add_argument("--out-json", default="reports/phase-37/corpus_quality.json",
                    help="output JSON path")
    args = ap.parse_args(argv)

    res = scan_corpus(args.history_dir)
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(f"scanned {res['n_files']} files; problems={res['n_problems']}; ok={res['ok']}")
    for p in res["problems"]:
        print(f"  DEFECT {p}: {res['files'][p]['status']} -> {res['files'][p]['issues']}")
    print(f"wrote {out}")
    # fail closed: a dirty corpus must not be reported as clean
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
