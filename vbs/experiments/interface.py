"""interface.py — the MCP `run_experiment` interface (ARENA.md §5.1, DIFFERENTIATION.md).

THE HEADLINE. When the VoI selector picks "resolve axis X for hypothesis H" and
that axis needs *new computation* rather than a cached lookup, it is dispatched
through one call — ``run_experiment(hypothesis, axis)`` — with a **pluggable
backend**. At least one backend produces genuine new computation on real data
(not a DB lookup): a frontier scientific model doing real inference IS the
experiment. The result updates H's card and the arena re-ranks. We rank → act →
re-rank, closing the loop the paper leaves open.

Backends (interchangeable behind this interface):
  * **Boltz-2** — binding-affinity prediction (the live demo backend).
  * **single-cell** — τ specificity / malignant-localisation on a real atlas.
  * **DNA/RNA LM** — Evo / Nucleotide Transformer scoring a sequence/variant.

Honest demo scope: interface universal, all three registered, ONE live (Boltz-2),
others registered stubs. This module implements the **registry + dispatch + card
update + cache fallback contract**; each backend file fills its own compute.
"""
from __future__ import annotations

from typing import Callable, Protocol

from ..arena.card import Axis, Evidence, HypothesisCard
from ..arena.hypothesis import Hypothesis


class ExperimentBackend(Protocol):
    """A pluggable experiment backend. ``run`` returns one Evidence for ``axis``."""

    name: str
    axis: Axis  # the card axis this backend resolves

    def run(self, hypothesis: Hypothesis) -> Evidence: ...


_REGISTRY: dict[str, ExperimentBackend] = {}


def register(backend: ExperimentBackend) -> ExperimentBackend:
    """Register a backend under its ``name`` (call at import time in backends/*)."""
    _REGISTRY[backend.name] = backend
    return backend


def available() -> list[str]:
    return sorted(_REGISTRY)


def backend_for_axis(axis: Axis) -> ExperimentBackend | None:
    """First registered backend that resolves ``axis`` (TODO: preference/cost order)."""
    axis = Axis(axis)
    return next((b for b in _REGISTRY.values() if b.axis == axis), None)


def run_experiment(hypothesis: Hypothesis, axis: Axis, card: HypothesisCard,
                   *, backend: str | None = None,
                   cache_get: Callable[[str, Axis], Evidence | None] | None = None) -> Evidence:
    """Resolve ``axis`` for ``hypothesis`` by running a frontier-model experiment.

    Contract (IMPLEMENTED): pick the backend (explicit name or by axis) → try the
    cache first (stage-safe fallback for slow GPU runs, DIFFERENTIATION.md) → run
    the backend → attach the resulting Evidence to ``card`` → return it. The
    *compute* lives in each backend; this is the universal dispatch + fold-in.
    """
    b = _REGISTRY[backend] if backend else backend_for_axis(axis)
    if b is None:
        raise LookupError(f"no experiment backend registered for axis={Axis(axis).value}")
    if cache_get is not None:
        cached = cache_get(hypothesis.hypothesis_id, Axis(axis))
        if cached is not None:
            card.put(cached)
            return cached
    ev = b.run(hypothesis)
    card.put(ev)
    return ev
