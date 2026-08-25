"""Typed, fail-closed configuration for the autonomous engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import math


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
class RiskLimits:
    max_daily_loss_usd: float = 2.0
    max_drawdown_pct: float = 5.0
    max_position_notional_usd: float = 25.0
    max_total_notional_usd: float = 25.0
    max_concurrent_positions: int = 1
    max_leverage: float = 3.0
    max_orders_per_minute: int = 2

    def __post_init__(self) -> None:
        for name in ("max_daily_loss_usd", "max_drawdown_pct", "max_position_notional_usd", "max_total_notional_usd", "max_leverage"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ConfigError(f"{name} must be finite and positive")
        if self.max_concurrent_positions <= 0 or self.max_orders_per_minute <= 0:
            raise ConfigError("position and order limits must be positive")


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "shadow"
    dry_run: bool = True
    testnet: bool = True
    kill_switch: bool = True
    withdrawals_enabled: bool = False
    provider: ProviderConfig = ProviderConfig()
    risk_limits: RiskLimits = RiskLimits()

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
    policy_raw = raw.get("policy")
    risk_limits = RiskLimits()
    if policy_raw is not None:
        if not isinstance(policy_raw, dict):
            raise ConfigError("policy must be a mapping")
        required = {"max_daily_loss_usd", "max_drawdown_pct", "max_position_notional_usd",
                    "max_total_notional_usd", "max_concurrent_positions", "max_leverage",
                    "max_orders_per_minute"}
        missing = sorted(required - policy_raw.keys())
        if missing:
            raise ConfigError("missing executable risk limits: " + ", ".join(missing))
        try:
            risk_limits = RiskLimits(**{key: policy_raw[key] for key in required})
        except (TypeError, ValueError) as exc:
            raise ConfigError("invalid executable risk limits") from exc
    return RuntimeConfig(mode=mode, dry_run=dry_run, testnet=testnet, kill_switch=kill_switch,
                         withdrawals_enabled=withdrawals, provider=provider, risk_limits=risk_limits)


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
