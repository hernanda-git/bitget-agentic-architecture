"""Detect whether runtime observations contain useful variation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class VariationResult:
    status: str
    samples: int
    distinct_samples: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _distinct(values: list[Any]) -> int:
    distinct: list[Any] = []
    for value in values:
        if not any(value == existing for existing in distinct):
            distinct.append(value)
    return len(distinct)


def assess_variation(values: Iterable[Any], *, minimum_samples: int = 3) -> VariationResult:
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be positive")
    samples = list(values)
    distinct_samples = _distinct(samples)
    if len(samples) < minimum_samples:
        return VariationResult("INSUFFICIENT_DATA", len(samples), distinct_samples,
                               f"need at least {minimum_samples} samples")
    if distinct_samples == 1:
        return VariationResult("FLATLINE", len(samples), distinct_samples,
                               "all samples are identical")
    return VariationResult("HEALTHY", len(samples), distinct_samples,
                           "samples vary")


def assess_runtime_health(metrics: Mapping[str, Iterable[Any]], *, minimum_samples: int = 3) -> dict[str, Any]:
    results = {name: assess_variation(values, minimum_samples=minimum_samples)
               for name, values in metrics.items()}
    status = "DEGRADED" if any(result.status == "FLATLINE" for result in results.values()) else "HEALTHY"
    if results and all(result.status == "INSUFFICIENT_DATA" for result in results.values()):
        status = "STARTING"
    return {"status": status, "minimum_samples": minimum_samples,
            "metrics": {name: result.to_dict() for name, result in results.items()}}
