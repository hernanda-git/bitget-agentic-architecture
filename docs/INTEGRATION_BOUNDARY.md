# Integration Boundary

This directory is a standalone implementation target for a fully agentic trading engine.

## Forbidden dependencies

Runtime code and tests must not:

- import `/opt/bots/bitget-listener`
- import code from `/root/bitget-listener`
- read `.env` files outside this directory
- read exchange credentials from another project
- restart or modify any systemd service
- make signed exchange calls during shadow/paper development

## Allowed dependencies

- standard-library code
- explicitly declared package dependencies
- recorded fixtures
- fake providers and fake exchanges
- public market-data adapters only in a later read-only phase

## Live integration boundary

Integration with the existing Bitget bot requires a separate migration plan and explicit deployment action. This repository must remain independently testable and must never depend on the live bot's internal modules.

## Safe default

The application starts in `shadow` mode with `dry_run=true`, `testnet=true`, `kill_switch=true`, and withdrawals disabled. A model response cannot change these values.
