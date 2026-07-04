"""Plot AUGC gain curves for one or more ranking files against a labels set.

Draws, for each ranking, the gain curve `augc.py` scores: x = fraction of the
candidate pool scanned (top -> bottom), y = fraction of positives recovered. The
random baseline (diagonal) and the perfect early-enrichment curve are drawn for
reference; each ranking's normalised AUGC is shown in the legend.

Output is a self-contained SVG (no third-party deps). If matplotlib is installed,
pass --mpl to render a PNG instead.

  python3 eval/plot_gain_curves.py \
      --labels eval/data/melanoma_anyclin.labels.json \
      --ranking eval/data/melanoma_anyclin.claude_priors_ranking.json \
      --ranking eval/data/melanoma_anyclin.opentargets_ranking.json \
      --out eval/data/melanoma_anyclin.gain_curves.svg

See eval/RANKING_FORMAT.md for the ranking schema and eval/augc.py for the metric.
"""

from __future__ import annotations

import argparse
import json

from augc import _load_labels, _normalise_ranking, augc

# Colour-blind-safe qualitative palette (Wong 2011), reused for each ranking.
_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442"]


def _curve_for(ranking_path: str, pool, positives) -> tuple[str, float, list[tuple[float, float]]]:
    rk = json.load(open(ranking_path))
    ranker = rk.get("meta", {}).get("ranker", ranking_path)
    ordered = _normalise_ranking(rk["ranking"], pool)
    value, curve = augc(ordered, positives)
    return ranker, round(value, 4), curve


def _perfect_curve(n_pool: int, n_pos: int) -> list[tuple[float, float]]:
    if n_pool == 0 or n_pos == 0:
        return [(0.0, 0.0), (1.0, 0.0)]
    return [(0.0, 0.0), (n_pos / n_pool, 1.0), (1.0, 1.0)]


def render_svg(series, perfect, out_path: str, title: str) -> None:
    """series: list of (label, augc, curve, colour). perfect: reference curve."""
    W, H = 780, 520
    m = {"l": 70, "r": 270, "t": 56, "b": 60}
    pw = W - m["l"] - m["r"]
    ph = H - m["t"] - m["b"]

    def X(x: float) -> float:
        return m["l"] + x * pw

    def Y(y: float) -> float:
        return m["t"] + (1 - y) * ph

    def path(points) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{X(x):.1f},{Y(y):.1f}"
            for i, (x, y) in enumerate(points)
        )

    p = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="system-ui,-apple-system,sans-serif">'
    )
    p.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    p.append(
        f'<text x="{m["l"]}" y="30" font-size="17" font-weight="600" fill="#111">'
        f"{title}</text>"
    )

    # Gridlines + axis ticks at 0, .25, .5, .75, 1.
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        gx, gy = X(t), Y(t)
        p.append(f'<line x1="{gx:.1f}" y1="{m["t"]}" x2="{gx:.1f}" y2="{m["t"]+ph}" '
                 f'stroke="#eee" stroke-width="1"/>')
        p.append(f'<line x1="{m["l"]}" y1="{gy:.1f}" x2="{m["l"]+pw}" y2="{gy:.1f}" '
                 f'stroke="#eee" stroke-width="1"/>')
        p.append(f'<text x="{gx:.1f}" y="{m["t"]+ph+20}" font-size="11" '
                 f'text-anchor="middle" fill="#555">{t:g}</text>')
        p.append(f'<text x="{m["l"]-10}" y="{gy+4:.1f}" font-size="11" '
                 f'text-anchor="end" fill="#555">{t:g}</text>')

    # Axis frame + labels.
    p.append(f'<rect x="{m["l"]}" y="{m["t"]}" width="{pw}" height="{ph}" '
             f'fill="none" stroke="#333" stroke-width="1"/>')
    p.append(f'<text x="{m["l"]+pw/2:.1f}" y="{H-16}" font-size="13" '
             f'text-anchor="middle" fill="#333">fraction of pool scanned</text>')
    p.append(f'<text x="18" y="{m["t"]+ph/2:.1f}" font-size="13" text-anchor="middle" '
             f'fill="#333" transform="rotate(-90 18 {m["t"]+ph/2:.1f})">'
             f"fraction of positives recovered</text>")

    # Reference curve (random diagonal only; per-labelset "perfect" varies, so it's
    # shown in the label-set legend rather than as one line).
    p.append(f'<path d="{path([(0,0),(1,1)])}" fill="none" stroke="#999" '
             f'stroke-width="1.5" stroke-dasharray="4 4"/>')

    # Ranking curves. colour = ranker, dash = label set.
    for label, value, curve, colour, dash, _ls in series:
        da = f' stroke-dasharray="{dash}"' if dash else ""
        p.append(f'<path d="{path(curve)}" fill="none" stroke="{colour}" '
                 f'stroke-width="2.5"{da}/>')

    # Legend — ranker (colour), then label-set (dash style), then random ref.
    lx, ly = m["l"] + pw + 24, m["t"] + 6
    y = ly
    p.append(f'<text x="{lx}" y="{y}" font-size="11" font-weight="600" fill="#666">ranker × label set</text>')
    for label, value, _c, colour, dash, ls in series:
        y += 24
        da = f' stroke-dasharray="{dash}"' if dash else ""
        p.append(f'<line x1="{lx}" y1="{y}" x2="{lx+26}" y2="{y}" stroke="{colour}" '
                 f'stroke-width="3"{da}/>')
        p.append(f'<text x="{lx+34}" y="{y+4}" font-size="11" fill="#222">'
                 f"{label} · {ls}  (AUGC {value:.3f})</text>")
    y += 30
    p.append(f'<line x1="{lx}" y1="{y}" x2="{lx+26}" y2="{y}" stroke="#999" '
             f'stroke-width="3" stroke-dasharray="4 4"/>')
    p.append(f'<text x="{lx+34}" y="{y+4}" font-size="11" fill="#222">random</text>')

    p.append("</svg>")
    open(out_path, "w").write("\n".join(p))


def render_mpl(series, perfect, out_path: str, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _MPL_DASH = {"": (0, ()), "6 4": (0, (6, 4)), "2 3": (0, (2, 3)), "1 3": (0, (1, 3))}
    fig, ax = plt.subplots(figsize=(7.6, 5.2))
    ax.plot([0, 1], [0, 1], "--", color="#999", lw=1.5, label="random")
    for label, value, curve, colour, dash, ls in series:
        ax.plot(*zip(*curve), color=colour, lw=2.5,
                linestyle=_MPL_DASH.get(dash, (0, ())),
                label=f"{label} · {ls} (AUGC {value:.3f})")
    ax.set_xlabel("fraction of pool scanned")
    ax.set_ylabel("fraction of positives recovered")
    ax.set_title(title)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right", fontsize=8, title="ranker × label set")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)


# Dash styles distinguish label sets (solid = first given, then dashed/dotted).
_DASHES = ["", "6 4", "2 3", "1 3"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot AUGC gain curves for ranking files.")
    ap.add_argument("--labels", action="append", metavar="LABELS_JSON",
                    help="a labels JSON; repeat to overlay label sets. "
                         "Prefix a display name with 'NAME:path' (e.g. 'preclinical:eval/data/x.json')")
    ap.add_argument("--ranking", action="append", required=True, metavar="RANKING_JSON",
                    help="a ranking file (repeatable); colour distinguishes rankers")
    ap.add_argument("--out", required=True, help="output path (.svg, or .png with --mpl)")
    ap.add_argument("--title", default="AUGC gain curves")
    ap.add_argument("--mpl", action="store_true", help="render with matplotlib (PNG) if installed")
    args = ap.parse_args()

    if not args.labels:
        ap.error("provide at least one --labels")

    # Each --labels may be 'NAME:path' or just 'path' (name derived from filename).
    label_sets = []
    for spec in args.labels:
        if ":" in spec and not spec.split(":", 1)[0].endswith(".json"):
            name, path = spec.split(":", 1)
        else:
            name, path = spec.split("/")[-1].replace(".labels.json", "").replace(".json", ""), spec
        label_sets.append((name, path))

    # series: colour = ranker (per --ranking), dash = label set (per --labels).
    series = []
    perfect = None
    for li, (ls_name, ls_path) in enumerate(label_sets):
        pool, positives = _load_labels(ls_path)
        if perfect is None:
            perfect = _perfect_curve(len(pool), len(positives))
        dash = _DASHES[li % len(_DASHES)]
        print(f"[{ls_name}] pool={len(pool)} positives={len(positives)}")
        for ri, rk_path in enumerate(args.ranking):
            label, value, curve = _curve_for(rk_path, pool, positives)
            series.append((label, value, curve, _PALETTE[ri % len(_PALETTE)], dash, ls_name))
            print(f"    {label}: AUGC = {value}")

    if args.mpl:
        render_mpl(series, perfect, args.out, args.title)
    else:
        render_svg(series, perfect, args.out, args.title)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
