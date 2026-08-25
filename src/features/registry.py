from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FeatureValue:
    feature_name: str
    feature_version: str
    source_snapshot_hash: str
    source_timestamp: int
    parameters: dict[str, Any]
    value: float

    def __post_init__(self) -> None:
        if not self.feature_name or not self.feature_version or not self.source_snapshot_hash:
            raise ValueError("feature identity is required")
        if self.source_timestamp <= 0:
            raise ValueError("feature timestamp is required")


def feature(name: str, value: float, snapshot_hash: str, timestamp: int, parameters: dict[str, Any], version: str = "technical-v1") -> FeatureValue:
    return FeatureValue(name, version, snapshot_hash, timestamp, dict(parameters), float(value))
