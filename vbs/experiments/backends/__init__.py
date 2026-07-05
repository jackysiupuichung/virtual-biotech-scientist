"""Pluggable experiment backends. Importing this package registers them all
(Boltz-2 live; single-cell + DNA/RNA-LM stubs) with vbs.experiments.interface."""
from . import boltz2, singlecell, dna_rna_lm  # noqa: F401  (side effect: register())
