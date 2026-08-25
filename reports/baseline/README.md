# Baseline evidence

This artifact records the standalone repository baseline before implementation work.

- Revision: `f5eac10f17cc80a5f0305eabf3907abf56fabdd8`
- Collected by: `scripts/baseline_check.py`
- Evidence JSON: `reports/baseline/latest.json`
- Runtime boundary: the checker scans only this repository's `src/` and `scripts/` trees. It does not inspect or access the deployed bot tree.

The baseline checker reports the live test collection count, compile status, git status, and forbidden runtime-boundary findings. Secret values are never read or printed.

## Known pre-change findings

These are plan-level findings carried forward from the existing repository and are not silently treated as fixed:

- paper entry can leave an open position in the current one-shot path;
- fixture shadow is distinct from real public-data shadow and is not evidence about live markets;
- replay and direct script invocation need continued hygiene verification;
- dashboard execution and credential boundaries require explicit tests;
- no funded execution is enabled by this project.

## Phase 0 gate evidence

- baseline JSON generated: yes
- focused baseline and boundary tests: passed
- compile check: passed
- clean-install verification: required before Phase 0 is closed
- signed calls: 0
- orders placed: 0
