"""singlecell.py — single-cell specificity backend (ARENA.md §5.1) — registered stub.

Resolves the TISSUE axis by computing per-gene cell-type specificity (the τ index)
and malignant-vs-stroma localisation on a real single-cell atlas (CELLxGENE) — the
very signal the paper shows predicts trial success. This backend WRAPS the migrated
``skills/celltype-specificity-profiler`` (A6), which already computes τ offline on
bundled real data (scanpy pbmc3k), so the compute is real; what's stubbed is the
adapter that maps its JSON output onto an Evidence record.
"""
from __future__ import annotations

from ...arena.card import Axis, Evidence
from ...arena.hypothesis import Hypothesis
from ..interface import register


class SingleCellBackend:
    name = "singlecell"
    axis = Axis.TISSUE

    def run(self, hypothesis: Hypothesis) -> Evidence:
        """Compute τ specificity for the target gene → TISSUE Evidence.

        TODO(B4): invoke skills/celltype-specificity-profiler/profiler.py for
        ``hypothesis.target`` on the relevant atlas (or its --demo fixture), read
        the τ specificity index (0 ubiquitous → 1 single-cell-restricted) and map
        τ → value directly (higher τ = better tissue specificity). The profiler is
        already migrated and offline-runnable, so this is an adapter, not new compute.
        """
        raise NotImplementedError(
            "single-cell backend not wired — call the migrated "
            "celltype-specificity-profiler and map tau → TISSUE value. See TODO(B4)."
        )
        # return Evidence(axis=Axis.TISSUE, value=tau, confidence=...,
        #                 cost=CostTier.EXPERIMENT, provenance="celltype-specificity-profiler",
        #                 detail={"tau": tau, "bimodality": ...})


register(SingleCellBackend())
