"""Testnet gate scaffold. It refuses production product types by construction."""
from __future__ import annotations

class ConfigGateError(ValueError): pass

def validate_testnet_config(mode: str, product_type: str, dry_run: bool) -> None:
    if mode != 'testnet': raise ConfigGateError('mode must be testnet')
    if product_type != 'SUSDT-FUTURES': raise ConfigGateError('only demo product type is allowed')
    if not dry_run: raise ConfigGateError('testnet scaffold requires dry_run')

def gate_status() -> str:
    return 'SCAFFOLD_ONLY_NO_SIGNED_CALLS'
