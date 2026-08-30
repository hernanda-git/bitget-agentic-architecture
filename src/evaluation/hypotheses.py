"""Independent strategy hypothesis registry.

The registry is deliberately separate from strategy selection and evaluation so
hypotheses remain auditable claims rather than hidden tuning configuration.
Each hypothesis is also bound to the directive sec. 3 factor ontology via a
``category`` field, so coverage of the factor space is measurable and promotion
cannot be claimed while whole categories remain unrepresented.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

from src.evaluation.factor_ontology import normalize_category

_REQUIRED = ("mechanism", "data", "features", "entry_exit", "cost_edge", "falsification", "failure_modes", "data_exclusions", "oos_gate")

# Canonical measured verdicts of the adaptation loop (directive sec. 5/7):
# keep what survives out-of-sample, kill what doesn't, hold while undecided.
OUTCOME_VERDICTS = frozenset({"keep", "kill", "hold"})


@dataclass(frozen=True)
class Outcome:
    """A fail-closed recorded verdict for a hypothesis in the adaptation loop."""

    verdict: str
    reason: str
    evidence: str = ""


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    title: str
    mechanism: str = ""
    data: str = ""
    features: tuple[str, ...] = ()
    category: str = ""
    entry_exit: str = ""
    cost_edge: str = ""
    falsification: str = ""
    failure_modes: str = ""
    data_exclusions: str = ""
    oos_gate: str = ""

    def validate(self):
        missing = [name for name in _REQUIRED if not getattr(self, name)]
        if missing: raise ValueError("missing hypothesis fields: " + ", ".join(missing))
        if not self.hypothesis_id or not self.title: raise ValueError("hypothesis_id and title are required")
        # Fail closed: a hypothesis must declare a known factor-ontology category.
        if not self.category:
            raise ValueError("hypothesis must declare a factor-ontology category")
        normalize_category(self.category)  # raises FactorOntologyError if unknown
        return self


class HypothesisRegistry:
    def __init__(self):
        self._items = {}
        self._outcomes = {}
    def register(self, hypothesis):
        hypothesis.validate()
        if hypothesis.hypothesis_id in self._items: raise ValueError("duplicate hypothesis_id")
        self._items[hypothesis.hypothesis_id] = hypothesis
    def get(self, hypothesis_id): return self._items[hypothesis_id]
    def as_dict(self): return {"hypotheses": [asdict(h) for h in self._items.values()]}
    def __iter__(self): return iter(self._items.values())
    def __len__(self): return len(self._items)

    def mark_outcome(self, hypothesis_id, verdict, reason, evidence=""):
        # Fail closed: a verdict can only be recorded for a registered hypothesis.
        if hypothesis_id not in self._items:
            raise ValueError(f"unknown hypothesis_id: {hypothesis_id!r}")
        # Fail closed: an unrecognized verdict is rejected, never coerced/aliased.
        v = verdict.lower() if isinstance(verdict, str) else ""
        if v not in OUTCOME_VERDICTS:
            raise ValueError(
                f"invalid outcome verdict: {verdict!r} (expected one of {sorted(OUTCOME_VERDICTS)})"
            )
        # Fail closed: every verdict is a decision and must be evidenced; a kill
        # especially so (directive sec. 7 -- kill without sentiment, with reason).
        if not reason or not str(reason).strip():
            raise ValueError("outcome requires a non-empty reason (evidence)")
        self._outcomes[hypothesis_id] = Outcome(v, str(reason).strip(), evidence or "")
    def outcome(self, hypothesis_id):
        return self._outcomes.get(hypothesis_id)
    def outcomes(self):
        return dict(self._outcomes)
