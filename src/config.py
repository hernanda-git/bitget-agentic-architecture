"""Typed, fail-closed configuration for the autonomous engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    name: str = "anthropic"
    model: str = ""
    base_url: str = ""
    timeout_seconds: float = 8.0
    max_retries: int = 1
    circuit_breaker_failures: int = 3


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "shadow"
    dry_run: bool = True
    testnet: bool = True
    kill_switch: bool = True
    withdrawals_enabled: bool = False
    provider: ProviderConfig = ProviderConfig()

    def __post_init__(self) -> None:
        if self.mode not in {"shadow", "paper", "testnet", "live"}:
            raise ConfigError(f"invalid mode: {self.mode}")
        if self.mode == "live" and (self.dry_run or self.testnet):
            raise ConfigError("live mode requires dry_run=false and testnet=false")
        if self.withdrawals_enabled:
            raise ConfigError("withdrawals are not supported")
        if self.provider.timeout_seconds <= 0:
            raise ConfigError("provider timeout must be positive")
        if self.provider.max_retries < 0 or self.provider.max_retries > 2:
            raise ConfigError("provider retries must be between 0 and 2")


def _bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{key} must be boolean")


def from_mapping(raw: dict[str, Any], deployment_gate: Path | None = None) -> RuntimeConfig:
    if not isinstance(raw, dict):
        raise ConfigError("configuration must be a mapping")
    provider_raw = raw.get("provider") or {}
    if not isinstance(provider_raw, dict):
        raise ConfigError("provider must be a mapping")
    mode = raw.get("mode", "shadow")
    dry_run = _bool(raw.get("dry_run", True), "dry_run")
    testnet = _bool(raw.get("testnet", True), "testnet")
    kill_switch = _bool(raw.get("kill_switch", True), "kill_switch")
    withdrawals = _bool(raw.get("withdrawals_enabled", False), "withdrawals_enabled")
    if mode == "live":
        gate = deployment_gate
        if gate is None:
            raise ConfigError("live mode requires an explicit deployment gate")
        try:
            enabled = gate.read_text().strip() == "ENABLE_LIVE_MODE"
        except OSError:
            enabled = False
        if not enabled:
            raise ConfigError("live mode requires an explicit deployment gate")
    provider = ProviderConfig(
        name=str(provider_raw.get("name", "anthropic")),
        model=str(provider_raw.get("model", "")),
        base_url=str(provider_raw.get("base_url", "")),
        timeout_seconds=float(provider_raw.get("timeout_seconds", 8)),
        max_retries=int(provider_raw.get("max_retries", 1)),
        circuit_breaker_failures=int(provider_raw.get("circuit_breaker_failures", 3)),
    )
    return RuntimeConfig(mode, dry_run, testnet, kill_switch, withdrawals, provider)


def load_yaml(path: Path, deployment_gate: Path | None = None) -> RuntimeConfig:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required to load YAML configuration") from exc
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except OSError as exc:
        raise ConfigError(f"cannot read configuration: {path}") from exc
    except Exception as exc:
        raise ConfigError("invalid YAML configuration") from exc
    return from_mapping(raw, deployment_gate=deployment_gate)
