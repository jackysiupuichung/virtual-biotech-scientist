"""Thin Open Targets Platform GraphQL client for the prioritisation eval.

Deterministic, snapshot-able access to:
  - the candidate pool (disease-associated targets, optionally chemical-probe filtered,
    mirroring Adaszewski & Schindler's `hasHighQualityChemicalProbes` filter), and
  - the clinical-outcome ground truth (target -> max clinical phase, from drugs in
    clinic for the disease).

No auth/key. See eval/OPENTARGETS_HARNESS.md for the field-level design and the schema
gotchas verified against the live API (Platform v4).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

API = "https://api.platform.opentargets.org/api/v4/graphql"

# Highest -> lowest, so a smaller index == later/more-advanced stage.
PHASE_ORDER = [
    "PHASE_4",
    "PHASE_3",
    "PHASE_2",
    "PHASE_1",
    "EARLY_PHASE_1",
    "PHASE_0",
    "PRECLINICAL",
]


def phase_rank(phase: str) -> int:
    """Rank a phase string; unknown/empty ranks last."""
    return PHASE_ORDER.index(phase) if phase in PHASE_ORDER else len(PHASE_ORDER)


def _gql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    if "errors" in payload:
        raise RuntimeError(payload["errors"][0]["message"])
    return payload["data"]


# --------------------------------------------------------------------------- #
# Disease id lookup
# --------------------------------------------------------------------------- #

_SEARCH = """
query($q:String!){
  search(queryString:$q, entityNames:["disease"]){ hits{ id name } }
}
"""


def search_disease(query: str, limit: int = 5) -> list[dict]:
    hits = _gql(_SEARCH, {"q": query})["search"]["hits"]
    return [{"id": h["id"], "name": h["name"]} for h in hits[:limit]]


# --------------------------------------------------------------------------- #
# Candidate pool
# --------------------------------------------------------------------------- #

_ASSOC = """
query($efo:String!, $size:Int!){
  disease(efoId:$efo){
    id name
    associatedTargets(page:{index:0, size:$size}){
      count
      rows{
        score
        target{ id approvedSymbol chemicalProbes{ isHighQuality } }
      }
    }
  }
}
"""


@dataclass
class Candidate:
    ensembl_id: str
    symbol: str
    ot_score: float
    high_quality_probe: bool


def candidates(efo: str, size: int = 500, probe_filter: bool = True) -> list[Candidate]:
    """Top-`size` disease-associated targets, ordered by OT association score.

    With `probe_filter` (default), keep only targets carrying >=1 high-quality
    chemical probe -- the paper's `hasHighQualityChemicalProbes` candidate filter.
    """
    disease = _gql(_ASSOC, {"efo": efo, "size": size})["disease"]
    if disease is None:
        raise ValueError(f"no disease for efoId={efo!r} (check the id via search_disease)")
    out: list[Candidate] = []
    for row in disease["associatedTargets"]["rows"]:
        t = row["target"]
        probes = t.get("chemicalProbes") or []
        hq = any((p or {}).get("isHighQuality") for p in probes)
        if probe_filter and not hq:
            continue
        out.append(
            Candidate(
                ensembl_id=t["id"],
                symbol=t["approvedSymbol"],
                ot_score=row["score"],
                high_quality_probe=hq,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Ground truth: target -> max clinical phase for this disease
# --------------------------------------------------------------------------- #

_GT = """
query($efo:String!){
  disease(efoId:$efo){
    drugAndClinicalCandidates{
      count
      rows{
        maxClinicalStage
        drug{ name drugType mechanismsOfAction{ rows{ targets{ approvedSymbol } } } }
      }
    }
  }
}
"""


def ground_truth(efo: str) -> dict[str, str]:
    """Map target symbol -> its most-advanced clinical phase for this disease.

    Derived from drugs in clinic for the disease, linked to targets via each drug's
    mechanism(s) of action. This is our retrospective positive label set.
    """
    disease = _gql(_GT, {"efo": efo})["disease"]
    if disease is None:
        raise ValueError(f"no disease for efoId={efo!r}")
    best: dict[str, str] = {}
    for row in disease["drugAndClinicalCandidates"]["rows"]:
        phase = row["maxClinicalStage"] or ""
        moa = row["drug"].get("mechanismsOfAction") or {}
        for m in moa.get("rows") or []:
            for t in m.get("targets") or []:
                sym = t["approvedSymbol"]
                if sym not in best or phase_rank(phase) < phase_rank(best[sym]):
                    best[sym] = phase
    return best


# --------------------------------------------------------------------------- #
# Per-target evidence fields (for building descriptive hypothesis cards)
# --------------------------------------------------------------------------- #

_TARGET = """
query($id:String!){
  target(ensemblId:$id){
    approvedSymbol approvedName functionDescriptions
    tractability{ modality value label }
    geneticConstraint{ constraintType score upperBin oe }
    safetyLiabilities{ event datasource }
    mousePhenotypes{ modelPhenotypeLabel }
    pathways{ pathway }
  }
}
"""


def target_evidence(ensembl_id: str) -> dict:
    """Real per-target fields from Open Targets, grouped for card assembly.

    Returns the raw material the axis builders summarise into findings:
      - tractability buckets (SM/AB/PROTAC) -> Tractability axis
      - geneticConstraint (LOEUF) -> Right Target
      - safetyLiabilities + mousePhenotypes -> Right Safety
      - functionDescriptions/pathways -> narrative overview
    Fields not carried here (single-cell tau, malignant fraction, patient stratum,
    competitive whitespace) are NOT in OT and must be synthesised downstream.
    """
    t = _gql(_TARGET, {"id": ensembl_id})["target"]
    if t is None:
        raise ValueError(f"no target for ensemblId={ensembl_id!r}")
    return {
        "symbol": t["approvedSymbol"],
        "name": t.get("approvedName"),
        "function": (t.get("functionDescriptions") or [None])[0],
        "tractability": t.get("tractability") or [],
        "genetic_constraint": t.get("geneticConstraint") or [],
        "safety_liabilities": [s["event"] for s in (t.get("safetyLiabilities") or [])],
        "mouse_phenotypes": [m["modelPhenotypeLabel"] for m in (t.get("mousePhenotypes") or [])],
        "pathways": [p["pathway"] for p in (t.get("pathways") or [])],
    }
