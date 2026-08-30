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
    def __init__(self): self._items = {}
    def register(self, hypothesis):
        hypothesis.validate()
        if hypothesis.hypothesis_id in self._items: raise ValueError("duplicate hypothesis_id")
        self._items[hypothesis.hypothesis_id] = hypothesis
    def get(self, hypothesis_id): return self._items[hypothesis_id]
    def as_dict(self): return {"hypotheses": [asdict(h) for h in self._items.values()]}
    def __iter__(self): return iter(self._items.values())
    def __len__(self): return len(self._items)
