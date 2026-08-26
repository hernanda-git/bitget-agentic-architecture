# Runtime wiring inventory

Captured `2026-08-26T23:18:00+07:00` (`Asia/Jakarta`) from revision `d47ac14ebb383e85d0504f8cd2ac7e035824f86f`. This is an inspection artifact only. No runtime code was changed in work unit 1.1.

| Entry point | Composition root | Provider | Exchange / ledger | Report | Classification |
|---|---|---|---|---|---|
| `scripts/northline_agentic_demo.py --mode shadow` | `_load_runner("run_autonomous_shadow.py")` -> `run_shadow` | none | `EventLedger`; fixture events | `write_run_report` | `fixture-shadow` |
| `scripts/northline_agentic_demo.py --mode paper` | `_load_runner("run_autonomous_paper.py")` -> `run_paper` -> `PaperLoop.process` | `FakeProvider` | `FakeExchange` + `EventLedger` | `write_run_report` | `paper` |
| `scripts/run_autonomous_paper.py` | `run_paper` -> `PaperLoop.process` | `FakeProvider` | `FakeExchange` + `EventLedger` | `write_run_report` | `paper` |
| `scripts/run_paper.py` | `run_paper_once` | none | `FakeExchange` + `EventLedger` | none | `paper` vertical slice |
| `scripts/run_autonomous_shadow.py` | `run_shadow` | none | `EventLedger` | `write_run_report` | `fixture-shadow` |
| `scripts/run_shadow.py` | `run_shadow` | none | `EventLedger` | none | `fixture-shadow` legacy slice |
| `scripts/run_public_shadow.py` | `run_public_shadow` | none | `BitgetPublicClient` + `EventLedger` | `write_shadow_report` | `public-shadow` |
| `src/runtime/paper_runtime.py` | `AutonomousPaperRuntime.process` | `AgentProvider` via `ProviderCircuit` | `FakeExchange` + `EventLedger` | caller-owned | `paper` runtime API |
| `src/paper_loop.py` | `PaperLoop.process` | `AgentProvider` via `run_cycle` | `FakeExchange` + `EventLedger` | caller-owned | `paper` runtime API |

## Duplication and bypass findings

- `src/runtime/paper_runtime.py` and `src/paper_loop.py` each implement the lifecycle from claim through terminal disposition, sizing, fill, protection, and reconciliation. Their event details and provider handling differ.
- `scripts/run_autonomous_paper.py` is the richest paper composition root and performs a deterministic protection-triggered close after each ENTER scenario. `scripts/run_paper.py` is a smaller entry-only slice without a terminal close.
- `scripts/run_autonomous_shadow.py` is fixture-only despite the generic `shadow` mode name. `scripts/run_public_shadow.py` is the only public-data shadow root and uses the unauthenticated public client.
- `scripts/northline_agentic_demo.py` dynamically imports runner files, so the launcher is a dispatcher rather than a lifecycle implementation.
- `scripts/ui_server.py` is a separate dashboard composition root and currently contains a credential-backed signed read path. It is not part of the offline launcher and remains a Phase 5 blocker.

## Mode boundary

- `fixture-shadow`: synthetic ledger observations, `network_calls=0`, `orders=0`.
- `public-shadow`: unauthenticated public market reads, `signed_calls=0`, `orders=0`, no simulated PnL claim.
- `paper`: fake exchange only, bounded cycles, no credentials or signed calls.
- `demo` and `live`: unsupported by the standalone launcher. The typed demo adapter is separate and not invoked by these roots.

## Next action

Create one canonical offline lifecycle interface and route the paper and fixture-shadow entrypoints through it without rewriting the fake exchange or ledger. Keep public-shadow as a distinct public-data composition root.
