"""Plot AUGC gain curves for one or more ranking files against a labels set.

Draws the gain curve `augc.py` scores: x = fraction of the candidate pool scanned
(top -> bottom), y = fraction of positives recovered. Each `--labels` set is its own
subplot (task); within a panel, colour = ranker. The random baseline (diagonal) and
that task's perfect early-enrichment curve are drawn for reference; each ranking's
normalised AUGC is shown in the panel legend.

Output is a self-contained SVG (no third-party deps). If matplotlib is installed,
pass --mpl to render a PNG instead.

  python3 eval/plot_gain_curves.py \
      --labels preclinical:eval/data/melanoma_anyclin.labels.json \
      --labels phase2:eval/data/melanoma.labels.json \
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


def render_svg(panels, out_path: str, title: str) -> None:
    """One subplot per task (label set).

    panels: list of (task_name, n_pos, n_pool, perfect_curve, rows) where
    rows is a list of (ranker_label, augc, curve, colour). Colour is consistent
    per ranker across panels.
    """
    n = len(panels)
    PW, PH = 340, 340        # plot area per panel
    ml, gap, mt = 60, 56, 64  # left margin, gap between panels, top margin
    mb, mr = 96, 30           # bottom (axis label + legend), right margin
    W = ml + n * PW + (n - 1) * gap + mr
    H = mt + PH + mb

    def path(points, x0, y0) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{x0 + x * PW:.1f},{y0 + (1 - y) * PH:.1f}"
            for i, (x, y) in enumerate(points)
        )

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="system-ui,-apple-system,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{ml}" y="32" font-size="17" font-weight="600" fill="#111">{title}</text>',
    ]

    for pi, (task, n_pos, n_pool, perfect, rows) in enumerate(panels):
        x0 = ml + pi * (PW + gap)
        y0 = mt

        # Per-panel title.
        p.append(f'<text x="{x0 + PW/2:.1f}" y="{y0 - 14}" font-size="13" '
                 f'font-weight="600" text-anchor="middle" fill="#333">'
                 f"{task}  ({n_pos}/{n_pool} positives)</text>")

        # Gridlines + ticks.
        for t in (0, 0.25, 0.5, 0.75, 1.0):
            gx, gy = x0 + t * PW, y0 + (1 - t) * PH
            p.append(f'<line x1="{gx:.1f}" y1="{y0}" x2="{gx:.1f}" y2="{y0+PH}" '
                     f'stroke="#eee" stroke-width="1"/>')
            p.append(f'<line x1="{x0}" y1="{gy:.1f}" x2="{x0+PW}" y2="{gy:.1f}" '
                     f'stroke="#eee" stroke-width="1"/>')
            p.append(f'<text x="{gx:.1f}" y="{y0+PH+18}" font-size="10" '
                     f'text-anchor="middle" fill="#666">{t:g}</text>')
            if pi == 0:
                p.append(f'<text x="{x0-8}" y="{gy+4:.1f}" font-size="10" '
                         f'text-anchor="end" fill="#666">{t:g}</text>')

        # Frame.
        p.append(f'<rect x="{x0}" y="{y0}" width="{PW}" height="{PH}" '
                 f'fill="none" stroke="#333" stroke-width="1"/>')

        # References: random diagonal + this task's perfect early-enrichment curve.
        p.append(f'<path d="{path([(0,0),(1,1)], x0, y0)}" fill="none" stroke="#999" '
                 f'stroke-width="1.4" stroke-dasharray="4 4"/>')
        p.append(f'<path d="{path(perfect, x0, y0)}" fill="none" stroke="#c8c8c8" '
                 f'stroke-width="1.4" stroke-dasharray="2 3"/>')

        # Ranking curves (colour = ranker).
        for _label, _value, curve, colour in rows:
            p.append(f'<path d="{path(curve, x0, y0)}" fill="none" stroke="{colour}" '
                     f'stroke-width="2.5"/>')

        # Per-panel legend, bottom-right inside the frame.
        ly = y0 + PH - 12 - (len(rows) - 1) * 18
        for ri, (label, value, _c, colour) in enumerate(rows):
            yy = ly + ri * 18
            p.append(f'<line x1="{x0+PW-160}" y1="{yy}" x2="{x0+PW-140}" y2="{yy}" '
                     f'stroke="{colour}" stroke-width="3"/>')
            p.append(f'<text x="{x0+PW-134}" y="{yy+4}" font-size="10.5" fill="#222">'
                     f"{label}  {value:.3f}</text>")

        # X axis label per panel.
        p.append(f'<text x="{x0+PW/2:.1f}" y="{y0+PH+40}" font-size="12" '
                 f'text-anchor="middle" fill="#333">fraction of pool scanned</text>')

    # Shared Y axis label.
    p.append(f'<text x="18" y="{mt+PH/2:.1f}" font-size="12" text-anchor="middle" '
             f'fill="#333" transform="rotate(-90 18 {mt+PH/2:.1f})">'
             f"fraction of positives recovered</text>")
    # Footnote: reference-line key.
    p.append(f'<text x="{ml}" y="{H-16}" font-size="10.5" fill="#888">'
             f"dashed = random · dotted = perfect early enrichment · number = AUGC</text>")

    p.append("</svg>")
    open(out_path, "w").write("\n".join(p))


def render_mpl(panels, out_path: str, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 4.6), sharey=True, squeeze=False)
    for ax, (task, n_pos, n_pool, perfect, rows) in zip(axes[0], panels):
        ax.plot([0, 1], [0, 1], "--", color="#999", lw=1.4, label="random")
        ax.plot(*zip(*perfect), ":", color="#c8c8c8", lw=1.4, label="perfect")
        for label, value, curve, colour in rows:
            ax.plot(*zip(*curve), color=colour, lw=2.5, label=f"{label} ({value:.3f})")
        ax.set_title(f"{task}  ({n_pos}/{n_pool} positives)", fontsize=11)
        ax.set_xlabel("fraction of pool scanned")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend(loc="lower right", fontsize=8)
    axes[0][0].set_ylabel("fraction of positives recovered")
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot AUGC gain curves for ranking files.")
    ap.add_argument("--labels", action="append", metavar="LABELS_JSON",
                    help="a labels JSON; repeat for one subplot per label set (task). "
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

    # One panel (subplot) per label set / task. Colour = ranker, consistent across panels.
    panels = []
    for ls_name, ls_path in label_sets:
        pool, positives = _load_labels(ls_path)
        perfect = _perfect_curve(len(pool), len(positives))
        print(f"[{ls_name}] pool={len(pool)} positives={len(positives)}")
        rows = []
        for ri, rk_path in enumerate(args.ranking):
            label, value, curve = _curve_for(rk_path, pool, positives)
            rows.append((label, value, curve, _PALETTE[ri % len(_PALETTE)]))
            print(f"    {label}: AUGC = {value}")
        panels.append((ls_name, len(positives), len(pool), perfect, rows))

    if args.mpl:
        render_mpl(panels, args.out, args.title)
    else:
        render_svg(panels, args.out, args.title)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
