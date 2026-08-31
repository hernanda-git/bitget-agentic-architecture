"""Fail-closed corpus-staleness observation for the autonomous heartbeat.

Reads the public-history corpus directory and reports how fresh the blessed
datasets are, using each dataset's ``fetched_at_ms`` (the honest acquisition
timestamp written by ``scripts.acquire_corpus``). Reports staleness HONESTLY:
a missing, empty, or unreadable corpus is reported stale — it is never invented
into "fresh". No network, no signed calls, no mutation of the corpus.

This is an observability check only (directive §7: watch corpus staleness). It
changes nothing about trading/research logic and makes no promotion claim.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# 7 days. Older than this and the corpus is treated as stale (fail closed).
DEFAULT_MAX_AGE_MS = 7 * 24 * 3600 * 1000


@dataclass(frozen=True)
class CorpusFreshness:
    present: bool
    datasets: int
    newest_ms: int | None
    oldest_ms: int | None
    max_age_ms: int
    stale: bool
    reason: str
    fresh_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_corpus_freshness(corpus_dir: Any, *, now_ms: int,
                               max_age_ms: int = DEFAULT_MAX_AGE_MS) -> CorpusFreshness:
    """Report corpus freshness from each dataset's ``fetched_at_ms``.

    Fail-closed: when no readable dataset carries a usable acquisition timestamp
    (missing dir, empty dir, only a manifest, or only corrupt files) the corpus
    is reported ``stale`` with ``present=False`` — never "fresh".
    """
    corpus_dir = Path(corpus_dir)
    fetched: list[int] = []
    if corpus_dir.is_dir():
        for f in sorted(corpus_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                # Unreadable file: do not invent freshness from it; skip it.
                continue
            fa = data.get("fetched_at_ms") if isinstance(data, dict) else None
            if isinstance(fa, int) and fa > 0:
                fetched.append(fa)

    if not fetched:
        return CorpusFreshness(
            present=False, datasets=0, newest_ms=None, oldest_ms=None,
            max_age_ms=max_age_ms, stale=True, reason="no_fresh_corpus", fresh_ms=None)

    newest_ms = max(fetched)
    oldest_ms = min(fetched)
    fresh_ms = now_ms - newest_ms
    stale = fresh_ms > max_age_ms
    return CorpusFreshness(
        present=True, datasets=len(fetched), newest_ms=newest_ms, oldest_ms=oldest_ms,
        max_age_ms=max_age_ms, stale=stale,
        reason="stale" if stale else "fresh", fresh_ms=fresh_ms)


def main() -> int:
    """CLI: print a fail-closed corpus-freshness report for ``data/history``."""
    import sys

    corpus_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/history")
    now_ms = int(__import__("time").time() * 1000)
    result = evaluate_corpus_freshness(corpus_dir, now_ms=now_ms)
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if not result.stale else 75


if __name__ == "__main__":
    raise SystemExit(main())
