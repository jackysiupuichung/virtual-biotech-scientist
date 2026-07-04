"""leaderboard.py — the arena leaderboard UI (ARENA.md §6 step 4) — Streamlit, SCAFFOLD.

The demo surface: a live Elo animation + a Pareto-front view + per-claim provenance
(every card value traces to the tool/experiment behind it). ARENA.md's minimal
viable arena is steps 1–4, and this is step 4.

SCAFFOLD: layout + the three panels are sketched against the real arena APIs
(vbs.arena.pareto, vbs.arena.tournament); the live-update wiring and the run driver
are the TODO. Run with:  streamlit run ui/leaderboard.py  (needs the `ui` extra).
"""
from __future__ import annotations


def render() -> None:
    """Draw the three-panel leaderboard. TODO(B8): wire to a live harness run."""
    try:
        import streamlit as st
    except ImportError:  # keep the package importable without the ui extra
        raise SystemExit("Streamlit not installed — `pip install -e '.[ui]'` then "
                         "`streamlit run ui/leaderboard.py`.")

    from vbs.cso.harness import run_demo

    st.set_page_config(page_title="Virtual Biotech Scientist — Arena", layout="wide")
    st.title("🧬 Prioritisation Arena")
    st.caption("Competing (target × disease × modality) hypotheses, ranked multi-objectively.")

    result = run_demo()  # TODO(B8): replace with a live, streaming harness run

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Elo leaderboard")
        # TODO(B8): animate rating changes match-by-match instead of the final board.
        st.table([{"hypothesis": k, "elo": round(v)} for k, v in result["elo"].items()])
    with col2:
        st.subheader("Pareto fronts")
        # TODO(B8): scatter across two chosen axes, colour by front index.
        for i, fr in enumerate(result["pareto_fronts"]):
            st.write(f"Front {i + 1}: {', '.join(fr)}")
    with col3:
        st.subheader("Provenance")
        # TODO(B8): per selected card, list each axis Evidence + its provenance string.
        st.write("Select a hypothesis to see per-axis evidence and its source.")


if __name__ == "__main__":
    render()
