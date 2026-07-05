#!/usr/bin/env python3
"""resolver.py — alias → canonical-ID normalization for the CSO knowledge graph.

The CSO graph ([kg.py](kg.py)) mints node ids from whatever symbol a routed step
happens to use — a mix of gene symbols (``MET``, ``EGFR``), protein/alias names
(``B7-H3``, which is the gene ``CD276``), and disease abbreviations (``LUAD``,
``NSCLC``). PrimeKG ([prometheux_reason.py](prometheux_reason.py), the ``kg_csv``
bind) keys its nodes on *canonical* identities only — it knows ``CD276``, not
``B7-H3``; ``lung adenocarcinoma``, not ``LUAD`` — so a name-join against PrimeKG
silently misses every alias. This module closes that gap.

**Two-stage resolution, live-first** (the configured design):

  1. **Open Targets ``mapIds``** (live GraphQL, batch) resolves a messy alias to a
     *canonical* identity: the approved gene symbol + Ensembl id for targets, an
     EFO/MONDO id for diseases. Verified live (2026-06-26): ``B7-H3`` →
     ``CD276`` / ``ENSG00000103855``; ``NSCLC`` → ``MONDO_0005233``.
  2. A small **curated expansion map** runs *before* Open Targets for inputs OT
     can't resolve on its own — clinical disease abbreviations. OT resolves
     ``NSCLC`` but NOT ``LUAD``; expanding ``LUAD`` → ``lung adenocarcinoma`` first
     makes OT return ``MONDO_0005061``. The map holds *expansions, not ids*, so it
     never goes stale against OT's id space.

For a **target**, the canonical *gene symbol* OT returns is then the join key into
PrimeKG's NCBI-keyed ``kg_csv`` (``CD276`` → ``80381``) — see
:func:`prometheux_reason`-side resolution. OT deliberately does not expose the NCBI
id (only Ensembl + HGNC), so PrimeKG remains the source of truth for the graph's
target ids; OT's job is purely *alias → canonical symbol*.

Open Targets is free and needs no auth. Any failure (network, rate-limit, no hit)
degrades to returning the input unresolved — never fabricates an id.

    python3 resolver.py B7-H3 MET LUAD NSCLC      # resolve a few terms
    python3 resolver.py --json EGFR
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"

# Clinical abbreviations Open Targets does not index as disease synonyms. We expand
# to the full disease name (which OT *does* resolve) rather than hardcode an id, so
# this map can't drift against OT's EFO/MONDO id space. Keys are lowercased.
# Verified: OT resolves the expanded names; it does NOT resolve these abbreviations.
DISEASE_EXPANSIONS = {
    "luad": "lung adenocarcinoma",
    "lusc": "lung squamous cell carcinoma",
    "nsclc": "non-small cell lung carcinoma",   # OT also resolves "NSCLC" directly
    "sclc": "small cell lung carcinoma",
    "crc": "colorectal carcinoma",
    "hcc": "hepatocellular carcinoma",
    "gbm": "glioblastoma",
    "aml": "acute myeloid leukemia",
    "tnbc": "triple-negative breast carcinoma",
    "pdac": "pancreatic ductal adenocarcinoma",
}

_MAPIDS_QUERY = (
    "query ($q: [String!]!, $e: [String!]!) { "
    "mapIds(queryTerms: $q, entityNames: $e) { "
    "mappings { term hits { id name entity } } } }"
)


@dataclass
class Resolution:
    """One resolved term. ``resolved`` is False when nothing canonical was found."""

    term: str                         # the original input string
    queried: str                      # what we actually sent to OT (post-expansion)
    entity: str                       # "target" | "disease"
    resolved: bool = False
    canonical_id: str = ""            # ENSG… (target) | EFO_…/MONDO_… (disease)
    canonical_name: str = ""          # approved symbol (target) | disease name
    source: str = "opentargets"
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _gql(query: str, variables: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:
    """POST a GraphQL query to Open Targets. Raises on transport/HTTP error."""
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        OT_GRAPHQL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _pick_hit(term: str, hits: list[dict[str, Any]], entity: str) -> dict[str, Any] | None:
    """Choose the best hit. ``mapIds`` is ranked but fuzzy (e.g. ``MET`` returns a
    secondary ``SLTM`` hit), so prefer a hit whose name equals the term, restricted
    to the requested entity; else fall back to the top hit of that entity."""
    same_entity = [h for h in hits if h.get("entity") == entity]
    if not same_entity:
        return None
    for h in same_entity:
        if h.get("name", "").lower() == term.lower():
            return h
    return same_entity[0]


def resolve(terms: list[str], entity: str = "target", *,
            timeout: float = 30.0) -> list[Resolution]:
    """Resolve a batch of alias strings to canonical Open Targets identities.

    ``entity`` is ``"target"`` (→ Ensembl id + approved symbol) or ``"disease"``
    (→ EFO/MONDO id + name). Disease abbreviations in :data:`DISEASE_EXPANSIONS`
    are expanded before the call. One GraphQL round-trip for the whole batch. On any
    failure each term degrades to an unresolved :class:`Resolution` (never invents).
    """
    # expand known disease abbreviations; remember the mapping back to the input
    queried_for: dict[str, str] = {}
    for t in terms:
        q = t
        if entity == "disease":
            q = DISEASE_EXPANSIONS.get(t.strip().lower(), t)
        queried_for[t] = q

    out: dict[str, Resolution] = {
        t: Resolution(term=t, queried=queried_for[t], entity=entity) for t in terms}

    try:
        data = _gql(_MAPIDS_QUERY,
                    {"q": list({queried_for[t] for t in terms}), "e": [entity]},
                    timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        for r in out.values():
            r.note = f"open targets unavailable ({exc}); unresolved"
        return list(out.values())

    # index OT's results by the queried term (post-expansion)
    by_term: dict[str, list[dict[str, Any]]] = {}
    for m in (data.get("data", {}).get("mapIds", {}) or {}).get("mappings", []):
        by_term[m.get("term", "")] = m.get("hits", []) or []

    for t, r in out.items():
        hit = _pick_hit(queried_for[t], by_term.get(queried_for[t], []), entity)
        if hit:
            r.resolved = True
            r.canonical_id = hit.get("id", "")
            r.canonical_name = hit.get("name", "")
            if queried_for[t] != t:
                r.note = f"expanded '{t}' → '{queried_for[t]}'"
        else:
            r.note = "no Open Targets hit"
    return list(out.values())


def resolve_one(term: str, entity: str = "target", **kw) -> Resolution:
    """Single-term convenience wrapper over :func:`resolve`."""
    return resolve([term], entity, **kw)[0]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Resolve gene/disease aliases to canonical Open Targets ids.")
    p.add_argument("terms", nargs="+", help="symbols/aliases/abbreviations to resolve")
    p.add_argument("--entity", choices=["target", "disease"], default="target")
    p.add_argument("--json", action="store_true", help="emit JSON")
    args = p.parse_args(argv)

    results = resolve(args.terms, args.entity)
    if args.json:
        print(json.dumps([r.to_json() for r in results], indent=2))
        return 0
    for r in results:
        if r.resolved:
            extra = f"  ({r.note})" if r.note else ""
            print(f"  {r.term:12s} → {r.canonical_name}  [{r.canonical_id}]{extra}")
        else:
            print(f"  {r.term:12s} → UNRESOLVED  ({r.note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
