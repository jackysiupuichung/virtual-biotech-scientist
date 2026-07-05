# The self-improving scientist

"Self-improving" is the most over-claimed phrase in agentic science. It usually conflates four
distinct things. This doc separates them, says which are **real for us** vs. **honest roadmap**, and
grounds each in a cross-domain precedent so the claim isn't hand-waving.

> **Why the honesty matters.** Judges who know the field can smell a fake learning loop. Our
> credibility comes from claiming exactly the three levels we can defend — and naming the fourth as a
> limit we *haven't* crossed, because crossing it needs real-world outcomes we don't have in 48h.

## The four levels

| Level | What improves | Loop closes on | Status |
| --- | --- | --- | --- |
| **A. Self-improving answer** | the ranking, within one query | the evidence it gathers | ✅ **have it** (the VoI loop) |
| **B. Self-improving hypotheses** | the candidate set itself | match outcomes | ✅ **build a slice** |
| **C. Self-improving toolkit** | the agent's own capabilities | gaps it hits | ✅ **one scripted instance** |
| **D. Self-improving judgement** | the scorer / weights / judge | ground-truth outcomes | ❌ **roadmap (honest limit)** |

```
self-improving ANSWER       ← VoI loop                    (have it)
self-improving HYPOTHESES   ← evolve the losers           (build a slice)
self-improving TOOLKIT      ← compose new tools on a gap  (one scripted demo)
──────────────────────────────────────────────────────────────────────────
self-improving JUDGEMENT    ← needs real trial outcomes   (direction, not claimed)
```

---

## Level A — self-improving answer (we already have this)

The Value-of-Information loop ([ARENA.md §5](ARENA.md#5-compute-budgeted-loop-the-ai-scientist-part))
*is* self-improvement of the answer: the system finds its own weakest belief, runs an experiment to
resolve it, and its ranking improves. We don't build anything new here — we **reframe** what we have.

- **Cross-domain precedent:** AI Co-Scientist — *"as the system spends more time reasoning and
  improving, the self-rated quality of results improve"*; higher Elo correlates with correctness.
- **Claim:** "the answer gets better the longer it runs, and it decides *for itself* what to resolve."

## Level B — self-improving hypotheses (the strongest new angle, build a slice)

Don't pick from a fixed menu — **invent better menu items by learning from what lost.** A hypothesis
that loses its arena matches is not discarded; it is **mutated** and re-entered:

- swap **modality** (ADC → bispecific → CAR-T),
- narrow the **patient stratum** (all-comers → antigen-high),
- flip the **mechanism/direction** (antagonise → degrade),

then the mutated variant re-enters the arena. Over rounds, the **population of ideas improves**, not
just the ranking of a fixed set. Keep a **diverse** front (one elite per niche), not just the single
best, to avoid collapsing to one idea.

- **Cross-domain precedent:** quality-diversity / evolutionary search — MAP-Elites (Mouret & Clune
  2015), **FunSearch** (Romera-Paredes et al., Nature 2024), **AlphaEvolve** (DeepMind 2025).
- **Demo:** "watch B7-H3→ADC lose on a safety axis, get mutated to B7-H3→ADC in an antigen-high
  stratum, and climb back." That *is* a scientist improving its own ideas.
- **Scope:** a small mutation operator + re-entry into the arena. Moderate effort; high legibility.

## Level C — self-improving toolkit (one scripted instance)

The most on-theme level, because **ToolUniverse natively supports creating tools from natural-language
descriptions and iteratively optimising tool specs.** So when the arena hits an axis no existing tool
covers, the agent **composes a new tool** from primitives, registers it, and uses it — the toolkit
grows when the scientist meets its own limits.

- **Cross-domain precedent:** program synthesis / self-extension — Voyager (skill library that grows
  as the agent hits new tasks), ToolUniverse's own tool-composition feature.
- **Demo:** one **scripted** case — e.g. "no tool gives spatial co-localisation of target + immune
  cells; the agent composes one from existing primitives and resolves the axis."
- **Scope (honest):** demonstrate **one** instance working, not a general capability. This is the
  riskiest level to get live — keep it bounded.

## Level D — self-improving judgement (honest roadmap, do NOT claim)

True self-improvement of *judgement* — the system learning that its safety-axis weighting was wrong
because a target it ranked #1 later failed in the clinic — requires **ground-truth outcomes**. That
feedback lives in real trial-success data (the paper's 55,984-trial analysis, which we cut from
scope). Without it, any "our AI learns to judge better" claim is unfounded.

- **Honest framing for the deck:** "The one thing it can't yet improve is its judgement — that needs
  real-world outcomes. Anchored to clinical-trial-success data, the arena's weights and judge could be
  calibrated against which ranked targets actually progressed. That's the roadmap, not a claim."
- **Why we say it anyway:** naming the limit is what makes levels A–C believable.

---

## The pitch

> *Most AI scientists improve their answer. Ours also improves its **hypotheses** — mutating the ideas
> that lose — and its **toolkit** — composing new tools when it hits its own limits. The only thing it
> can't yet improve is its **judgement**, because that needs real-world outcomes; that's the roadmap.*

See [DIFFERENTIATION.md](../background/DIFFERENTIATION.md) for how this layers onto the experiment loop, and
[DIRECTIONS.md](../background/DIRECTIONS.md) for the evolving-hypotheses and tool-composition entries.
