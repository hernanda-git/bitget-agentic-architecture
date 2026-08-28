"""Fail-closed corpus acquisition for public Bitget history.

Acquires a manifest of ``(symbol, granularity, max_candles)`` datasets via the
read-only ``BitgetPublicClient`` (or any object exposing ``fetch_candles`` /
``fetch_history_funding_rate``), validates every dataset through the unified
data-quality gate (structural ``ok`` + wick-spike gate + coverage gate),
persists ONLY validated datasets, and finalizes a corpus manifest describing the
blessed corpus.

No signing, credentials, orders, or accounts are touched. Network access is
limited to the unauthenticated public candle/funding endpoints. Any dataset that
fails the gate is refused closed: it is never written and the corpus is not
blessed until every requested dataset passes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market.history import (
    acquire_dataset,
    coverage_gate,
    data_quality_report,
    load_dataset,
    wick_spike_gate,
)


@dataclass(frozen=True)
class CorpusEntry:
    symbol: str
    granularity: str
    candle_count: int
    path: str
    quality: dict


@dataclass
class CorpusResult:
    entries: list[CorpusEntry] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    acquired: int = 0
    skipped: int = 0


class CorpusAcquisitionError(RuntimeError):
    """Raised when one or more requested datasets fail the quality gate.

    Carries the partial ``CorpusResult`` so a caller can still bless the
    individually-valid datasets that were written before the refusal.
    """

    def __init__(self, message: str, result: CorpusResult | None = None):
        super().__init__(message)
        self.result = result


def _filename(symbol: str, granularity: str) -> str:
    return f"{symbol}_{granularity}.json"


def _gate_passes(report: Any, wick_spike_threshold_bps: float,
                 max_missing_fraction: float) -> bool:
    return (
        report.ok
        and wick_spike_gate(report, max_wick_spike_bps=wick_spike_threshold_bps)
        and coverage_gate(report, max_missing_fraction=max_missing_fraction)
    )


def _entry(symbol: str, gran: str, ds: Any, report: Any, path: str) -> CorpusEntry:
    return CorpusEntry(symbol=symbol, granularity=gran, candle_count=len(ds.candles),
                       path=path, quality=report.as_dict())


async def acquire_corpus(client, specs, out_dir, *, force: bool = False,
                          wick_spike_threshold_bps: float = 5000.0,
                          max_missing_fraction: float = 0.25,
                          fetched_at_ms: int | None = None) -> CorpusResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = CorpusResult()

    for spec in specs:
        symbol = spec["symbol"]
        gran = spec["granularity"]
        max_candles = int(spec["max_candles"])
        end_time_ms = spec.get("end_time_ms")
        target = out_dir / _filename(symbol, gran)

        # Idempotent reuse of an existing validated dataset.
        if target.exists() and not force:
            ds = load_dataset(target)
            report = data_quality_report(ds, wick_spike_threshold_bps=wick_spike_threshold_bps)
            if not _gate_passes(report, wick_spike_threshold_bps, max_missing_fraction):
                raise CorpusAcquisitionError(
                    f"existing dataset {target} failed quality gate", result)
            result.entries.append(_entry(symbol, gran, ds, report, str(target)))
            result.skipped += 1
            continue

        ds = await acquire_dataset(client, symbol, gran, end_time_ms=end_time_ms,
                                   max_candles=max_candles, fetched_at_ms=fetched_at_ms)
        report = data_quality_report(ds, wick_spike_threshold_bps=wick_spike_threshold_bps)
        if not _gate_passes(report, wick_spike_threshold_bps, max_missing_fraction):
            result.rejected.append({
                "symbol": symbol, "granularity": gran,
                "reason": "quality_gate", "quality": report.as_dict(),
            })
            continue  # fail closed: do NOT write the bad dataset

        target.write_text(json.dumps(ds.to_dict(), indent=2, sort_keys=True) + "\n")
        result.entries.append(_entry(symbol, gran, ds, report, str(target)))
        result.acquired += 1

    if result.rejected:
        raise CorpusAcquisitionError(
            "corpus acquisition refused closed for "
            f"{len(result.rejected)} dataset(s): "
            + ", ".join(f"{r['symbol']}({r['granularity']})" for r in result.rejected),
            result)
    return result


def write_corpus_manifest(out_dir, entries, manifest_name: str = "corpus_manifest.json") -> str:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_ms": int(time.time() * 1000),
        "datasets": [
            {"symbol": e.symbol, "granularity": e.granularity,
             "candle_count": e.candle_count, "path": e.path, "quality": e.quality}
            for e in entries
        ],
    }
    path = out_dir / manifest_name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return str(path)


# Phase 35 default expansion set: liquid, diverse USDT-perp symbols not yet in the
# corpus, chosen for breadth across market caps and regimes.
DEFAULT_SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "LTCUSDT", "BCHUSDT", "TRXUSDT", "DOTUSDT",
    "NEARUSDT", "ATOMUSDT", "UNIUSDT", "MATICUSDT", "AAVEUSDT", "FILUSDT",
    "ETCUSDT", "XLMUSDT", "EOSUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "INJUSDT",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire a corpus of public Bitget history (fail-closed)")
    parser.add_argument("--out-dir", default="data/history")
    parser.add_argument("--symbols", default=None,
                        help="comma-separated symbols; default is the Phase 35 expansion set")
    parser.add_argument("--granularity", default="1m")
    parser.add_argument("--max-candles", type=int, default=2500)
    parser.add_argument("--end-time-ms", type=int, default=None,
                        help="fetch backward from this timestamp; default = now")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--wick-spike-threshold-bps", type=float, default=5000.0)
    parser.add_argument("--max-missing-fraction", type=float, default=0.25)
    parser.add_argument("--manifest-name", default="corpus_manifest.json")
    args = parser.parse_args()

    from src.market.bitget_public import BitgetPublicClient, PublicMarketError

    symbols = [s.strip().upper() for s in (args.symbols or ",".join(DEFAULT_SYMBOLS)).split(",") if s.strip()]
    specs = [{"symbol": s, "granularity": args.granularity, "max_candles": args.max_candles,
              "end_time_ms": args.end_time_ms} for s in symbols]

    client = BitgetPublicClient(venue="bitget", product_type="SUSDT-FUTURES")
    print(f"[acquire_corpus] requesting {len(specs)} symbols @ {args.granularity}, "
          f"max_candles={args.max_candles}, force={args.force}")

    entries, rejected = acquire_corpus_tolerant(
        client, specs, args.out_dir, force=args.force,
        wick_spike_threshold_bps=args.wick_spike_threshold_bps,
        max_missing_fraction=args.max_missing_fraction)

    if not entries:
        print("[acquire_corpus] no datasets acquired; aborting manifest write")
        return 2

    manifest = write_corpus_manifest(args.out_dir, entries, args.manifest_name)
    print(f"[acquire_corpus] acquired={len(entries)} rejected={len(rejected)} -> manifest {manifest}")
    for r in rejected:
        print(f"[acquire_corpus] rejected {r['symbol']}({r['granularity']}): {r['reason']}")
    return 0


def acquire_corpus_tolerant(client, specs, out_dir, *, force: bool = False,
                             wick_spike_threshold_bps: float = 5000.0,
                             max_missing_fraction: float = 0.25,
                             fetched_at_ms: int | None = None):
    """Acquire per symbol so one bad symbol does not abort the whole corpus.

    Quality rejections still fail closed per dataset; network errors
    (``PublicMarketError``) are reported and skipped, never silently accepted.
    Returns ``(entries, rejected)`` where ``rejected`` lists the failed specs.
    """
    from src.market.bitget_public import PublicMarketError

    entries: list = []
    rejected: list[dict] = []
    for spec in specs:
        try:
            res = asyncio.run(acquire_corpus(
                client, [spec], out_dir, force=force,
                wick_spike_threshold_bps=wick_spike_threshold_bps,
                max_missing_fraction=max_missing_fraction, fetched_at_ms=fetched_at_ms))
            entries.extend(res.entries)
        except CorpusAcquisitionError as exc:
            if exc.result is not None:
                entries.extend(exc.result.entries)
            rejected.append({"symbol": spec["symbol"], "granularity": spec["granularity"],
                             "reason": "quality_gate", "detail": str(exc)})
        except PublicMarketError as exc:
            rejected.append({"symbol": spec["symbol"], "granularity": spec["granularity"],
                             "reason": "network", "detail": str(exc)})
    return entries, rejected


if __name__ == "__main__":
    raise SystemExit(main())
