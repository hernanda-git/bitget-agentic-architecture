# Phase 0 summary: freeze scope and baseline

Status: `PASSED`

## Evidence

- Baseline revision: `f5eac10f17cc80a5f0305eabf3907abf56fabdd8`
- Baseline artifact: `reports/baseline/latest.json`
- Test collection recorded by the checker: `153`
- Clean virtualenv installation: passed
- Clean virtualenv full suite: `153 passed`
- Compile check: passed
- Boundary tests: `4 passed`
- Network calls: `0`
- Signed calls: `0`
- Orders placed: `0`
- `/opt/bots/bitget-listener`: not accessed or modified

## Changes

- Added `scripts/baseline_check.py` with secret-redacting baseline collection.
- Added `tests/test_baseline_check.py`.
- Declared `PyYAML`, `pytest`, and `pytest-asyncio` dependencies required by the clean-install contract.
- Added `requirements-lock.txt`.
- Added baseline documentation and phase report.

## Findings carried forward

The existing paper path, fixture-only shadow path, replay/direct-script hygiene, and UI credential boundary remain implementation work. No profitability or execution claim is made.

## Gate decision

Phase 0 is complete. Phase 1 may begin. Funded execution remains disabled.
