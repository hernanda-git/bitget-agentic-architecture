# Phase 60 — Corpus Staleness Cleared via Fresh Public-History Acquisition

**Status:** completed; infrastructure unblocking phase; no profitability claim.
**Safety:** offline public-history replay only; shadow mode; no signed calls, no orders, no live execution.

## Why this phase

Phase 59's next alpha gate identified corpus staleness as the blocking issue (`should_park_heavy_work: True`). The blessed corpus had drifted past the 7-day freshness window, making any heavy evaluation untrustworthy. This phase acquires fresh public Bitget history to clear the staleness gate and restore the ability to run trustworthy walk-forward evaluation.

## Changes

- `scripts/acquire_corpus.py` — invoked with `--force --max-candles 2500 --symbols BTCUSDT,ETHUSDT,ADAUSDT --granularity 1m` to refresh the blessed corpus.
- `data/history/BTCUSDT_1m.json`, `ETHUSDT_1m.json`, `ADAUSDT_1m.json` — refreshed datasets (2500 candles each, validated through the unified data-quality gate).
- `data/history/corpus_manifest.json` — updated manifest reflecting fresh acquisition timestamps.
- `data/heartbeat/last.json`, `data/heartbeat/ticks.jsonl` — heartbeat tick recorded.

## RED / GREEN / mutation evidence

- **RED verified:** The corpus staleness gate was already enforced by `should_park_heavy_work()` returning `True` when `corpus_freshness.stale == True`. The pre-existing test `tests/test_heartbeat_status.py::test_should_park_returns_true_when_corpus_stale` captures this.
- **GREEN verified:** After fresh acquisition, `should_park_heavy_work()` returns `False` and `corpus_freshness.stale == False`. Full test battery passes.
- **No mutation needed:** This phase is infrastructure/unblocking — the staleness gate logic was not modified.

## Verification battery

- **compileall:** clean
- **Full pytest:** 733 passed / 4 skipped / 0 failed
- **Secret scan:** clean (all hits are prose references, not credentials)
- **/opt/bots/bitget-listener boundary:** no references in any committed source or test
- **Resource guard:** passes (memory ~32GB, disk ~13% used, inodes ~87% free)
- **`should_park_heavy_work`:** returns `False` (corpus fresh)

## Honest measurement

| Dataset | Candles | Status |
|---|---:|---|
| BTCUSDT 1m | 2500 | Fresh (stale=False) |
| ETHUSDT 1m | 2500 | Fresh (stale=False) |
| ADAUSDT 1m | 2500 | Fresh (stale=False) |

The corpus staleness gate is cleared. Heavy evaluation is now unblocked.

## Honest status

This phase clears the infrastructure blocker (corpus staleness) so that subsequent phases can run trustworthy evaluation on fresh public data. No strategy profitability is claimed. The deterministic promotion gate (`NEGATIVE_NET_PNL`) remains the only thing that may unblock promotion. Baseline remains negative. Promotion remains blocked.

## Next alpha gate

With the corpus refreshed and `should_park_heavy_work=False`, the next phase can now run the full evaluation pipeline on real public history. Per the standing directive priority order, the next bounded alpha-directed phase should derive a structurally distinct funding/basis or flow hypothesis testable on the existing dataset with purged OOS validation. Do not promote H-003 or the current breakout family. No profitability claim is allowed.
