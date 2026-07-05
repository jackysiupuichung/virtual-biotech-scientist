"""Render a Pareto agent run's domination graph as a self-contained, clickable HTML page.

    python arena/pareto_agent/visualize.py --result arena/pareto_test_run.json

Nodes are the run's hypotheses, colored by status (front / dominated /
red-flagged). Edges are every pairwise comparison the agent made: solid
arrows are domination edges, dashed amber lines are tradeoff/unresolved
comparisons that did not produce a dominance decision. Clicking an edge opens
a panel with the full comparison_summary and per-axis rationale behind it.
Clicking a red-flagged node shows why it was removed before Pareto analysis.
Optionally pass --hypotheses to label nodes with target/disease/modality
instead of just their id. The page is pannable (drag) and zoomable
(scroll / pinch / +- buttons).
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

NODE_R = 24
COL_GAP = 150
ROW_GAP_WITHIN_BAND = 100
BAND_GAP = 220
MAX_PER_ROW = 7
MARGIN = 80

STATUS_CSS_VAR = {
    "front": "--status-front",
    "dominated": "--status-dominated",
    "red_flagged": "--status-critical",
}
STATUS_LABEL = {
    "front": "Pareto front",
    "dominated": "Dominated",
    "red_flagged": "Red-flagged (removed pre-Pareto)",
}
STATUS_ORDER = ["front", "dominated", "red_flagged"]

EDGE_CSS_VAR = {
    "dominance": "--edge-dominance",
    "tradeoff": "--edge-tradeoff",
}
EDGE_LABEL = {
    "dominance": "Domination",
    "tradeoff": "Tradeoff / unresolved",
}


def _load_json(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def _hypothesis_labels(hypotheses_path: Optional[str]) -> Dict[str, Dict[str, str]]:
    if not hypotheses_path:
        return {}
    doc = _load_json(hypotheses_path)
    hyps = doc["hypotheses"] if isinstance(doc, dict) and "hypotheses" in doc else doc
    labels = {}
    for h in hyps:
        labels[h["id"]] = {
            "target": h.get("target", {}).get("symbol", ""),
            "disease": h.get("disease", {}).get("name", ""),
            "modality": h.get("modality", ""),
        }
    return labels


def _wrap_into_rows(ordered_ids: List[str], max_per_row: int) -> List[List[str]]:
    if not ordered_ids:
        return []
    rows = [ordered_ids[i : i + max_per_row] for i in range(0, len(ordered_ids), max_per_row)]
    return rows


def _layout(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, float]]:
    """Front band on top, dominated band below (ordered near their dominator to
    reduce edge crossings), red-flagged band at the bottom. Each band wraps
    long rows so no single row gets absurdly wide, and every band is centered
    on a shared vertical axis so the whole graph reads as one composition
    instead of a corner-hugging cluster."""
    by_status: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        by_status[n["status"]].append(n)

    front = by_status.get("front", [])
    dominated = by_status.get("dominated", [])
    red_flagged = by_status.get("red_flagged", [])

    front_order = {n["hypothesis_id"]: i for i, n in enumerate(front)}
    dominators_of: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        if e["dominator"] and e["dominated"]:
            dominators_of[e["dominated"]].append(e["dominator"])

    def sort_key(n: Dict[str, Any]) -> float:
        doms = dominators_of.get(n["hypothesis_id"], [])
        ranked = [front_order[d] for d in doms if d in front_order]
        return min(ranked) if ranked else len(front) + 1

    dominated_sorted = [n["hypothesis_id"] for n in sorted(dominated, key=sort_key)]
    front_ids = [n["hypothesis_id"] for n in front]
    red_flagged_ids = [n["hypothesis_id"] for n in red_flagged]

    bands = [
        ("front", front_ids),
        ("dominated", dominated_sorted),
        ("red_flagged", red_flagged_ids),
    ]

    max_row_width = 0.0
    band_rows: List[Tuple[str, List[List[str]]]] = []
    for status, ids in bands:
        if not ids:
            continue
        rows = _wrap_into_rows(ids, MAX_PER_ROW)
        band_rows.append((status, rows))
        for row in rows:
            max_row_width = max(max_row_width, (len(row) - 1) * COL_GAP)

    positions: Dict[str, Dict[str, float]] = {}
    y = MARGIN
    for status, rows in band_rows:
        for row in rows:
            row_width = (len(row) - 1) * COL_GAP
            start_x = MARGIN + (max_row_width - row_width) / 2
            for i, hid in enumerate(row):
                positions[hid] = {"x": start_x + i * COL_GAP, "y": y}
            y += ROW_GAP_WITHIN_BAND
        y += BAND_GAP - ROW_GAP_WITHIN_BAND

    all_x = [p["x"] for p in positions.values()] or [0]
    all_y = [p["y"] for p in positions.values()] or [0]
    bbox = {
        "min_x": min(all_x) - MARGIN,
        "max_x": max(all_x) + MARGIN,
        "min_y": min(all_y) - MARGIN,
        "max_y": max(all_y) + MARGIN + 40,  # room for sublabels under the last row
    }
    return positions, bbox


def _escape_for_script_tag(raw_json: str) -> str:
    # Prevent a literal "</script>" inside embedded JSON from closing the tag early.
    return raw_json.replace("</", "<\\/")


def render_html(result: Dict[str, Any], labels: Dict[str, Dict[str, str]]) -> str:
    graph = result["domination_graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    positions, bbox = _layout(nodes, edges)

    payload = {
        "nodes": nodes,
        "edges": edges,
        "positions": positions,
        "labels": labels,
        "run_metadata": result.get("run_metadata", {}),
        "bbox": bbox,
    }
    payload_json = _escape_for_script_tag(json.dumps(payload))

    legend_items = "".join(
        f'<span class="legend-item"><span class="dot" style="background:var({cssvar})"></span>{STATUS_LABEL[status]}</span>'
        for status, cssvar in STATUS_CSS_VAR.items()
    )
    edge_legend_items = "".join(
        f'<span class="legend-item"><span class="edge-swatch {kind}" style="border-color:var({cssvar})"></span>{EDGE_LABEL[kind]}</span>'
        for kind, cssvar in EDGE_CSS_VAR.items()
    )

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Pareto domination graph</title>
<style>
  :root {{
    --bg: #fcfcfb; --fg: #0b0b0b; --panel-bg: #f7f7f5; --border: rgba(11,11,11,0.10);
    --muted: #6b7178; --accent: #2e6dd4;
    --status-front: #0ca30c; --status-dominated: #767b86; --status-critical: #d03b3b;
    --edge-dominance: #757c8c; --edge-tradeoff: #b5730d;
    --shadow-sm: 0 1px 2px rgba(11,11,11,0.14), 0 1px 1px rgba(11,11,11,0.08);
    --shadow-md: 0 4px 14px rgba(11,11,11,0.12), 0 1px 3px rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #16181c; --fg: #e8e9eb; --panel-bg: #1c1f24; --border: rgba(255,255,255,0.10);
      --muted: #9aa0a8; --accent: #6fa1ff;
      --status-front: #16c157; --status-dominated: #8a90a0; --status-critical: #e2635f;
      --edge-dominance: #8891a3; --edge-tradeoff: #e0a53e;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.45), 0 1px 1px rgba(0,0,0,0.3);
      --shadow-md: 0 6px 20px rgba(0,0,0,0.4), 0 2px 6px rgba(0,0,0,0.35);
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #16181c; --fg: #e8e9eb; --panel-bg: #1c1f24; --border: rgba(255,255,255,0.10);
    --muted: #9aa0a8; --accent: #6fa1ff;
    --status-front: #16c157; --status-dominated: #8a90a0; --status-critical: #e2635f;
    --edge-dominance: #8891a3; --edge-tradeoff: #e0a53e;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.45), 0 1px 1px rgba(0,0,0,0.3);
    --shadow-md: 0 6px 20px rgba(0,0,0,0.4), 0 2px 6px rgba(0,0,0,0.35);
  }}
  :root[data-theme="light"] {{
    --bg: #fcfcfb; --fg: #0b0b0b; --panel-bg: #f7f7f5; --border: rgba(11,11,11,0.10);
    --muted: #6b7178; --accent: #2e6dd4;
    --status-front: #0ca30c; --status-dominated: #767b86; --status-critical: #d03b3b;
    --edge-dominance: #757c8c; --edge-tradeoff: #b5730d;
    --shadow-sm: 0 1px 2px rgba(11,11,11,0.14), 0 1px 1px rgba(11,11,11,0.08);
    --shadow-md: 0 4px 14px rgba(11,11,11,0.12), 0 1px 3px rgba(11,11,11,0.10);
  }}

  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    display: flex; flex-direction: column;
  }}
  h1 {{ font-size: 16px; margin: 0; letter-spacing: -0.01em; }}
  header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 22px; border-bottom: 1px solid var(--border);
    flex-wrap: wrap; gap: 10px; flex: 0 0 auto;
    box-shadow: var(--shadow-sm); position: relative; z-index: 3;
  }}
  .meta {{ color: var(--muted); font-size: 12.5px; }}
  .legend {{ display: flex; gap: 16px; font-size: 12.5px; color: var(--muted); flex-wrap: wrap; }}
  .legend-group {{ display: flex; gap: 16px; align-items: center; }}
  .legend-sep {{ width: 1px; height: 14px; background: var(--border); }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .edge-swatch {{ width: 20px; height: 0; border-top-width: 2px; border-top-style: solid; display: inline-block; }}
  .edge-swatch.tradeoff {{ border-top-style: dashed; }}

  .layout {{ display: flex; flex: 1 1 auto; min-height: 0; }}
  .graph-wrap {{ flex: 1 1 auto; position: relative; min-width: 0; background: var(--bg); }}
  svg {{ display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; }}
  svg.panning {{ cursor: grabbing; }}

  .zoom-controls {{
    position: absolute; right: 14px; bottom: 14px; display: flex; flex-direction: column;
    gap: 6px; z-index: 2;
  }}
  .zoom-controls button {{
    width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--border);
    background: var(--panel-bg); color: var(--fg); font-size: 15px; cursor: pointer;
    box-shadow: var(--shadow-sm); transition: filter .12s ease, transform .12s ease;
  }}
  .zoom-controls button:hover {{ filter: brightness(1.12); transform: translateY(-1px); }}
  .zoom-controls button:active {{ transform: translateY(0); }}
  .zoom-hint {{
    position: absolute; left: 14px; bottom: 14px; color: var(--muted); font-size: 11.5px;
    z-index: 2; background: var(--panel-bg); padding: 4px 9px; border-radius: 999px;
    border: 1px solid var(--border); box-shadow: var(--shadow-sm);
  }}

  .node circle {{
    stroke: var(--bg); stroke-width: 3px; cursor: pointer;
    filter: drop-shadow(0 1px 3px rgba(11,11,11,0.22));
    transition: filter .15s ease, transform .15s ease;
  }}
  .node .status-front {{ fill: var(--status-front); }}
  .node .status-dominated {{ fill: var(--status-dominated); }}
  .node .status-red_flagged {{ fill: var(--status-critical); }}
  .node text {{ fill: #fff; font-size: 11px; font-weight: 600; text-anchor: middle; pointer-events: none; }}
  .node .sublabel-bg {{ fill: var(--bg); opacity: 0.82; pointer-events: none; }}
  .node .sublabel {{ fill: var(--muted); font-size: 10.5px; font-weight: 500; text-anchor: middle; pointer-events: none; }}
  .node:hover circle {{
    filter: drop-shadow(0 3px 8px rgba(11,11,11,0.32)) brightness(1.1);
    transform: scale(1.08); transform-origin: center; transform-box: fill-box;
  }}

  .edge-hit {{ stroke: transparent; stroke-width: 16px; fill: none; cursor: pointer; }}
  .edge-line {{
    stroke-width: 2px; fill: none; pointer-events: none;
    transition: stroke-width .15s ease, opacity .15s ease, stroke .15s ease;
  }}
  .edge.dominance .edge-line {{ stroke: var(--edge-dominance); }}
  .edge.tradeoff .edge-line {{ stroke: var(--edge-tradeoff); stroke-dasharray: 5 4; }}
  .edge:hover .edge-line {{ stroke: var(--accent); stroke-width: 3px; }}
  .edge.selected .edge-line {{ stroke: var(--accent); stroke-width: 3.2px; }}
  .edge.incident .edge-line {{ stroke-width: 3px; }}
  .edge.dimmed .edge-line {{ opacity: 0.22; }}
  #arrow path {{ fill: var(--edge-dominance); }}
  #arrow-accent path {{ fill: var(--accent); }}

  .panel {{
    width: 420px; flex: 0 0 auto; border-left: 1px solid var(--border);
    padding: 20px 22px; overflow-y: auto; background: var(--panel-bg);
    box-shadow: -6px 0 16px -12px rgba(11,11,11,0.25);
  }}
  .panel h2 {{ font-size: 15px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  .panel .rel {{ color: var(--muted); margin-bottom: 14px; }}
  .empty-hint {{ color: var(--muted); }}

  .axis-block {{
    border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px;
    margin-bottom: 10px; background: var(--bg); box-shadow: var(--shadow-sm);
    transition: box-shadow .15s ease;
  }}
  .axis-block:hover {{ box-shadow: var(--shadow-md); }}
  .axis-block .axis-head {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 6px;
  }}
  .axis-name {{ font-weight: 600; text-transform: capitalize; }}
  .axis-tag {{
    font-size: 11px; padding: 1px 7px; border-radius: 999px; border: 1px solid var(--border);
  }}
  .axis-tag.A_better, .axis-tag.B_better {{ color: var(--status-front); border-color: var(--status-front); }}
  .axis-tag.tie {{ color: var(--muted); }}
  .axis-tag.incomparable, .axis-tag.insufficient_evidence {{ color: var(--status-critical); border-color: var(--status-critical); }}
  .confidence {{ font-size: 11px; color: var(--muted); }}
  .rationale {{ margin: 6px 0; }}
  .ev-list {{ margin: 4px 0 0; padding-left: 18px; color: var(--muted); font-size: 12.5px; }}
  .summary-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }}
  .chip {{
    font-size: 11.5px; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--border);
    background: var(--bg);
  }}
</style>
</head>
<body>
<header>
  <h1>Pareto domination graph</h1>
  <div class="legend">
    <span class="legend-group">{legend_items}</span>
    <span class="legend-sep"></span>
    <span class="legend-group">{edge_legend_items}</span>
  </div>
  <div class="meta" id="meta"></div>
</header>
<div class="layout">
  <div class="graph-wrap">
    <svg id="graph">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z"></path>
        </marker>
        <marker id="arrow-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z"></path>
        </marker>
      </defs>
      <g id="edges"></g>
      <g id="nodes"></g>
    </svg>
    <div class="zoom-hint">Scroll to zoom &middot; drag to pan</div>
    <div class="zoom-controls">
      <button id="zoom-in" title="Zoom in">+</button>
      <button id="zoom-out" title="Zoom out">&minus;</button>
      <button id="zoom-fit" title="Fit to view">&#9633;</button>
    </div>
  </div>
  <div class="panel" id="panel">
    <p class="empty-hint">Click an edge to see the comparison that produced it. Click a node to see the hypothesis.</p>
  </div>
</div>

<script type="application/json" id="data">{payload_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const NODE_R = {NODE_R};

const svgNS = "http://www.w3.org/2000/svg";
const svg = document.getElementById('graph');
const nodesG = document.getElementById('nodes');
const edgesG = document.getElementById('edges');
const panel = document.getElementById('panel');
const meta = document.getElementById('meta');

const md = DATA.run_metadata || {{}};
meta.textContent = `${{md.num_input_hypotheses ?? '?'}} hypotheses -> ${{md.num_surviving_hypotheses ?? '?'}} survived red flags -> ${{md.num_front_hypotheses ?? '?'}} on front (${{md.num_domination_edges ?? '?'}} domination, ${{md.num_tradeoff_comparisons ?? '?'}} tradeoff comparisons)`;

function posOf(id) {{ return DATA.positions[id]; }}

function labelFor(id) {{
  const l = DATA.labels[id];
  if (!l) return {{ sub: '', full: id }};
  const full = [l.target, l.disease, l.modality].filter(Boolean).join(' \\u2022 ');
  let sub = l.target || '';
  if (sub.length > 16) sub = sub.slice(0, 15) + '\\u2026';
  return {{ sub, full: full || id }};
}}

function elWithAttrs(tag, attrs) {{
  const el = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}}

// --- edges (drawn first, under nodes) ---
// Curved as a gentle quadratic bow, alternating sides by index, so edges that
// fan out from/converge on the same hub node separate instead of overlapping
// in a single straight bundle (which is both illegible and hard to click).
const edgeEls = [];
const incidentEdges = {{}}; // node id -> [edge indices]

DATA.edges.forEach((edge, i) => {{
  const isDominance = !!(edge.dominator && edge.dominated);
  const fromId = isDominance ? edge.dominator : edge.hypothesis_a;
  const toId = isDominance ? edge.dominated : edge.hypothesis_b;
  const from = posOf(fromId), to = posOf(toId);
  if (!from || !to) return;

  (incidentEdges[fromId] ||= []).push(i);
  (incidentEdges[toId] ||= []).push(i);

  const dx = to.x - from.x, dy = to.y - from.y;
  const dist = Math.hypot(dx, dy) || 1;
  const ux = dx / dist, uy = dy / dist;
  const px = -uy, py = ux;
  const endPad = isDominance ? 8 : 2;
  const x1 = from.x + ux * (NODE_R + 2), y1 = from.y + uy * (NODE_R + 2);
  const x2 = to.x - ux * (NODE_R + endPad), y2 = to.y - uy * (NODE_R + endPad);
  const bow = Math.min(28, dist * 0.16) * (i % 2 === 0 ? 1 : -1);
  const mx = (x1 + x2) / 2 + px * bow, my = (y1 + y2) / 2 + py * bow;
  const d = `M${{x1}},${{y1}} Q${{mx}},${{my}} ${{x2}},${{y2}}`;

  const kind = isDominance ? 'dominance' : 'tradeoff';
  const g = elWithAttrs('g', {{ class: `edge ${{kind}}`, 'data-idx': i }});
  // Wide invisible stroke so the clickable area is much bigger than the
  // visible 2px line - the line itself stays thin and elegant.
  const hit = elWithAttrs('path', {{ class: 'edge-hit', d }});
  const lineAttrs = {{ class: 'edge-line', d }};
  if (isDominance) lineAttrs['marker-end'] = 'url(#arrow)';
  const line = elWithAttrs('path', lineAttrs);
  g.appendChild(hit);
  g.appendChild(line);
  g.addEventListener('click', () => selectEdge(i, g));
  if (isDominance) {{
    g.addEventListener('mouseenter', () => line.setAttribute('marker-end', 'url(#arrow-accent)'));
    g.addEventListener('mouseleave', () => {{
      if (!g.classList.contains('selected')) line.setAttribute('marker-end', 'url(#arrow)');
    }});
  }}
  edgesG.appendChild(g);
  edgeEls.push(g);
}});

// --- nodes ---
DATA.nodes.forEach(n => {{
  const p = posOf(n.hypothesis_id);
  if (!p) return;
  const g = elWithAttrs('g', {{ class: 'node', transform: `translate(${{p.x}},${{p.y}})` }});
  const circle = elWithAttrs('circle', {{ r: NODE_R, class: `status-${{n.status}}` }});
  const text = elWithAttrs('text', {{ y: 4 }});
  text.textContent = n.hypothesis_id;
  g.appendChild(circle);
  g.appendChild(text);

  const lbl = labelFor(n.hypothesis_id);
  const title = elWithAttrs('title', {{}});
  title.textContent = lbl.full;
  g.appendChild(title);

  if (lbl.sub) {{
    // A translucent backing plate keeps the sublabel legible where a curved
    // edge happens to pass underneath it.
    const bg = elWithAttrs('rect', {{
      class: 'sublabel-bg', x: -34, y: NODE_R + 5, width: 68, height: 14, rx: 4,
    }});
    const sub = elWithAttrs('text', {{ class: 'sublabel', y: NODE_R + 15 }});
    sub.textContent = lbl.sub;
    g.appendChild(bg);
    g.appendChild(sub);
  }}

  g.addEventListener('click', () => selectNode(n));
  g.addEventListener('mouseenter', () => highlightIncident(n.hypothesis_id));
  g.addEventListener('mouseleave', clearIncidentHighlight);
  nodesG.appendChild(g);
}});

function highlightIncident(hypothesisId) {{
  const incident = new Set(incidentEdges[hypothesisId] || []);
  edgeEls.forEach((g, i) => {{
    g.classList.toggle('incident', incident.has(i));
    g.classList.toggle('dimmed', !incident.has(i));
  }});
}}
function clearIncidentHighlight() {{
  edgeEls.forEach(g => {{ g.classList.remove('incident'); g.classList.remove('dimmed'); }});
}}

let selectedEdgeEl = null;

function clearSelection() {{
  if (selectedEdgeEl) {{
    selectedEdgeEl.classList.remove('selected');
    const prevLine = selectedEdgeEl.querySelector('.edge-line');
    if (selectedEdgeEl.classList.contains('dominance')) prevLine.setAttribute('marker-end', 'url(#arrow)');
  }}
  selectedEdgeEl = null;
}}

function axisTagText(rel, edge) {{
  if (rel === 'A_better') return `${{edge.hypothesis_a}} better`;
  if (rel === 'B_better') return `${{edge.hypothesis_b}} better`;
  return {{ tie: 'tie', incomparable: 'incomparable',
            insufficient_evidence: 'insufficient evidence' }}[rel] || rel;
}}

function renderEvidence(title, items) {{
  if (!items || !items.length) return '';
  return `<div class="rationale"><strong>${{title}}:</strong><ul class="ev-list">${{
    items.map(x => `<li>${{escapeHtml(x)}}</li>`).join('')
  }}</ul></div>`;
}}

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}

function selectEdge(i, g) {{
  clearSelection();
  g.classList.add('selected');
  selectedEdgeEl = g;
  if (g.classList.contains('dominance')) {{
    g.querySelector('.edge-line').setAttribute('marker-end', 'url(#arrow-accent)');
  }}

  const edge = DATA.edges[i];
  const summary = edge.comparison_summary || {{}};
  const isDominance = !!(edge.dominator && edge.dominated);

  let title, chips;
  if (isDominance) {{
    title = `${{edge.dominator}} dominates ${{edge.dominated}}`;
    chips = (summary.strictly_better_axes || [])
      .map(a => `<span class="chip">${{a}} \\u2192 dominator</span>`).join('');
  }} else {{
    title = `${{edge.hypothesis_a}} vs ${{edge.hypothesis_b}} \\u2014 tradeoff / unresolved`;
    const forA = (summary.strictly_better_axes_for_A || [])
      .map(a => `<span class="chip">${{a}} \\u2192 ${{edge.hypothesis_a}}</span>`).join('');
    const forB = (summary.strictly_better_axes_for_B || [])
      .map(a => `<span class="chip">${{a}} \\u2192 ${{edge.hypothesis_b}}</span>`).join('');
    chips = forA + forB;
  }}

  const axisOrder = ['right_target','right_tissue','right_safety','right_patient','right_commercial','tractability'];
  const axisHtml = axisOrder.filter(a => edge.axis_comparisons[a]).map(a => {{
    const c = edge.axis_comparisons[a];
    return `<div class="axis-block">
      <div class="axis-head">
        <span class="axis-name">${{a.replace(/_/g, ' ')}}</span>
        <span class="axis-tag ${{c.relation}}">${{axisTagText(c.relation, edge)}}</span>
      </div>
      <div class="confidence">confidence: ${{c.confidence}}</div>
      <div class="rationale">${{escapeHtml(c.rationale)}}</div>
      ${{renderEvidence('Decisive evidence', c.decisive_evidence)}}
      ${{renderEvidence('Missing evidence', c.missing_evidence)}}
    </div>`;
  }}).join('');

  panel.innerHTML = `
    <h2>${{title}}</h2>
    <div class="rel">${{summary.overall_relation || ''}}${{!isDominance && summary.reason ? ' \\u2014 ' + summary.reason : ''}}</div>
    <div class="summary-row">${{chips}}</div>
    ${{axisHtml}}
  `;
}}

const SEVERITY_TAG_CLASS = {{ critical: 'incomparable', major: 'B_better', minor: 'tie' }};

function renderRedFlagDetail(detail) {{
  if (!detail) return '';
  const flagBlocks = (detail.red_flags || []).map(f => `
    <div class="axis-block">
      <div class="axis-head">
        <span class="axis-name">${{escapeHtml(f.category).replace(/_/g, ' ')}}</span>
        <span class="axis-tag ${{SEVERITY_TAG_CLASS[f.severity] || 'tie'}}">${{f.severity}}</span>
      </div>
      <div class="rationale">${{escapeHtml(f.reason)}}</div>
    </div>
  `).join('');
  return `
    <div class="rationale"><strong>Why removed:</strong> ${{escapeHtml(detail.rationale)}}</div>
    ${{flagBlocks}}
  `;
}}

function selectNode(n) {{
  clearSelection();
  const lbl = DATA.labels[n.hypothesis_id] || {{}};
  const chips = `
      ${{lbl.target ? `<span class="chip">target: ${{escapeHtml(lbl.target)}}</span>` : ''}}
      ${{lbl.disease ? `<span class="chip">disease: ${{escapeHtml(lbl.disease)}}</span>` : ''}}
      ${{lbl.modality ? `<span class="chip">modality: ${{escapeHtml(lbl.modality)}}</span>` : ''}}
  `;

  if (n.status === 'red_flagged') {{
    panel.innerHTML = `
      <h2>${{n.hypothesis_id}}</h2>
      <div class="rel">status: red-flagged (removed before Pareto analysis)</div>
      <div class="summary-row">${{chips}}</div>
      ${{renderRedFlagDetail(n.red_flag_detail)}}
    `;
    return;
  }}

  panel.innerHTML = `
    <h2>${{n.hypothesis_id}}</h2>
    <div class="rel">status: ${{n.status}}</div>
    <div class="summary-row">${{chips}}</div>
    <p class="empty-hint">Click an edge touching this node to see the comparison behind it.</p>
  `;
}}

// --- zoom / pan (SVG viewBox-based) ---
const bbox = DATA.bbox;
const contentBox = {{
  x: bbox.min_x, y: bbox.min_y,
  w: bbox.max_x - bbox.min_x, h: bbox.max_y - bbox.min_y,
}};

// Pad contentBox to match the container's aspect ratio so the initial view
// fills the panel instead of letterboxing (preserveAspectRatio="meet" would
// otherwise leave dead space on whichever axis doesn't constrain the fit).
function fitToContainer(box) {{
  const rect = svg.getBoundingClientRect();
  const containerAspect = rect.width / rect.height;
  const contentAspect = box.w / box.h;
  let w = box.w, h = box.h;
  if (contentAspect > containerAspect) {{
    h = w / containerAspect;
  }} else {{
    w = h * containerAspect;
  }}
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  return {{ x: cx - w / 2, y: cy - h / 2, w, h }};
}}

const fit = fitToContainer(contentBox);
let viewBox = {{ ...fit }};

function applyViewBox() {{
  svg.setAttribute('viewBox', `${{viewBox.x}} ${{viewBox.y}} ${{viewBox.w}} ${{viewBox.h}}`);
}}
applyViewBox();

const MIN_ZOOM_W = fit.w * 0.08;
const MAX_ZOOM_W = fit.w * 4;

function zoomAt(clientX, clientY, factor) {{
  const rect = svg.getBoundingClientRect();
  const mx = viewBox.x + (clientX - rect.left) / rect.width * viewBox.w;
  const my = viewBox.y + (clientY - rect.top) / rect.height * viewBox.h;
  let newW = viewBox.w * factor;
  if (newW < MIN_ZOOM_W || newW > MAX_ZOOM_W) return;
  const newH = viewBox.h * factor;
  viewBox = {{
    x: mx - (mx - viewBox.x) * factor,
    y: my - (my - viewBox.y) * factor,
    w: newW, h: newH,
  }};
  applyViewBox();
}}

svg.addEventListener('wheel', (e) => {{
  e.preventDefault();
  const factor = Math.pow(1.0015, e.deltaY);
  zoomAt(e.clientX, e.clientY, factor);
}}, {{ passive: false }});

let isPanning = false;
let panStart = null;

svg.addEventListener('pointerdown', (e) => {{
  if (e.target.closest('.node') || e.target.closest('.edge')) return;
  isPanning = true;
  svg.classList.add('panning');
  panStart = {{ x: e.clientX, y: e.clientY, vb: {{ ...viewBox }} }};
  svg.setPointerCapture(e.pointerId);
}});
svg.addEventListener('pointermove', (e) => {{
  if (!isPanning) return;
  const rect = svg.getBoundingClientRect();
  const dx = (e.clientX - panStart.x) * panStart.vb.w / rect.width;
  const dy = (e.clientY - panStart.y) * panStart.vb.h / rect.height;
  viewBox = {{ ...panStart.vb, x: panStart.vb.x - dx, y: panStart.vb.y - dy }};
  applyViewBox();
}});
function endPan() {{ isPanning = false; svg.classList.remove('panning'); }}
svg.addEventListener('pointerup', endPan);
svg.addEventListener('pointerleave', endPan);

document.getElementById('zoom-in').addEventListener('click', () => {{
  const rect = svg.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 0.8);
}});
document.getElementById('zoom-out').addEventListener('click', () => {{
  const rect = svg.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1.25);
}});
document.getElementById('zoom-fit').addEventListener('click', () => {{
  viewBox = {{ ...fit }};
  applyViewBox();
}});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, help="Pareto agent run JSON (from run.py)")
    parser.add_argument("--hypotheses", default=None, help="original hypotheses fixture, for node labels")
    parser.add_argument("--out", default=None, help="output HTML path (default: alongside --result)")
    args = parser.parse_args()

    result = _load_json(args.result)
    labels = _hypothesis_labels(args.hypotheses)
    html = render_html(result, labels)

    out_path = args.out or os.path.splitext(args.result)[0] + "_graph.html"
    with open(out_path, "w") as f:
        f.write(html)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
