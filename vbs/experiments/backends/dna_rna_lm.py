"""dna_rna_lm.py — DNA/RNA language-model backend (ARENA.md §5.1) — registered stub.

Resolves the TARGET axis by scoring a sequence or variant with a genomic language
model — Evo or the Nucleotide Transformer — e.g. variant-effect / constraint
signal supporting the "does modulating it cause the disease effect?" question.
Registered behind the same interface as Boltz-2; a stub for the demo (honest scope:
one live backend, others registered stubs — DIFFERENTIATION.md).
"""
from __future__ import annotations

from ...arena.card import Axis, Evidence
from ...arena.hypothesis import Hypothesis
from ..interface import register


class DnaRnaLMBackend:
    name = "dna_rna_lm"
    axis = Axis.TARGET

    def run(self, hypothesis: Hypothesis) -> Evidence:
        """Score the target sequence/variant with a genomic LM → TARGET Evidence.

        TODO(B4): call Evo / Nucleotide Transformer (via ToolUniverse if exposed,
        else a hosted endpoint) for ``hypothesis.target``; map the variant-effect /
        constraint score to a [0,1] target-validity value.
        """
        raise NotImplementedError(
            "DNA/RNA-LM backend not wired — score sequence/variant with Evo / "
            "Nucleotide Transformer and map → TARGET value. See TODO(B4)."
        )


register(DnaRnaLMBackend())
