"""boltz2.py — Boltz-2 binding-affinity backend (ARENA.md §5.1) — the LIVE demo backend.

Resolves the TRACTABILITY axis by predicting binding affinity of a candidate
ligand against the target, via ToolUniverse's Boltz-2 tool
(``Boltz2_predict_binding_affinity``). A diffusion model computing on real
structure IS the experiment — not a database lookup.

SCAFFOLD: the call site + Evidence mapping are stubbed. Demo risk (DIFFERENTIATION.md):
Boltz-2 is slow/GPU-hungry, so the design mandates **pre-compute + cache**, and the
run_experiment cache fallback (interface.py) covers a stalled live run. Fill ``run``
with the ToolUniverse client call (vbs/tooluniverse/client.py) + normalisation.
"""
from __future__ import annotations

from ...arena.card import Axis, Evidence
from ...arena.hypothesis import Hypothesis
from ..interface import register


class Boltz2Backend:
    name = "boltz2"
    axis = Axis.TRACTABILITY

    def run(self, hypothesis: Hypothesis) -> Evidence:
        """Predict binding affinity → normalise to a [0,1] tractability value.

        TODO(B4): call ToolUniverse ``Boltz2_predict_binding_affinity`` for
        (target structure, candidate ligand); map predicted pIC50/affinity to
        [0,1] (higher affinity → higher tractability value); set confidence from
        the model's own uncertainty if reported. Needs NVIDIA_API_KEY for the
        hosted path (see .env.example) and a cached result for the demo fallback.
        """
        raise NotImplementedError(
            "Boltz-2 backend not wired — call ToolUniverse Boltz2_predict_binding_affinity "
            "and normalise affinity → tractability [0,1]. See TODO(B4)."
        )
        # Shape the implementation must return:
        # return Evidence(axis=Axis.TRACTABILITY, value=..., confidence=...,
        #                 cost=CostTier.EXPERIMENT, provenance="Boltz2_predict_binding_affinity",
        #                 detail={"affinity": ...})


register(Boltz2Backend())
