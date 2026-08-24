from pathlib import Path

import pytest

from src.config import ConfigError, RuntimeConfig, from_mapping


def test_defaults_are_fail_closed():
    config = from_mapping({})
    assert config == RuntimeConfig()
    assert config.mode == "shadow"
    assert config.dry_run is True
    assert config.testnet is True
    assert config.kill_switch is True
    assert config.withdrawals_enabled is False


def test_live_requires_explicit_gate(tmp_path: Path):
    with pytest.raises(ConfigError, match="deployment gate"):
        from_mapping({"mode": "live", "dry_run": False, "testnet": False}, tmp_path / "gate")


def test_live_gate_is_exact(tmp_path: Path):
    gate = tmp_path / "gate"
    gate.write_text("wrong")
    with pytest.raises(ConfigError, match="deployment gate"):
        from_mapping({"mode": "live", "dry_run": False, "testnet": False}, gate)
    gate.write_text("ENABLE_LIVE_MODE\n")
    config = from_mapping({"mode": "live", "dry_run": False, "testnet": False}, gate)
    assert config.mode == "live"


def test_withdrawals_are_always_rejected():
    with pytest.raises(ConfigError, match="withdrawals"):
        from_mapping({"withdrawals_enabled": True})


def test_invalid_types_are_rejected():
    with pytest.raises(ConfigError, match="dry_run"):
        from_mapping({"dry_run": "false"})
