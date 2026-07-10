# I built a virtual biotech scientist over a weekend. Here's what it taught me.

*Inspired by Future Bio's "AI Scientists" event in London. Which I applied to, and did not get into.*

---

So I signed up for Future Bio's "AI Scientists" event in London and didn't get picked. Oh well, no notes, we move. But the idea would not leave me alone, so a few friends and I grabbed pizza and beer and built our own version over a weekend: a multi-agent AI scientist for drug-target discovery.

Not a chatbot that talks about biology. The goal was to copy the actual process a target-discovery biotech runs: a team of scientists collaborating, arguing, and converging on a go or no-go call. You ask it something like "is PMEL a good target in melanoma?", and a panel of specialist agents goes out, pulls real evidence from real databases, reviews each other's work, decides which experiments are worth running, and hands back a decision with every claim traced to the tool that produced it.

Here is what building it actually taught me.

## A team of agents beats one big model

One agent trying to do everything is a generalist that's mediocre at every step. A real therapeutics org isn't one person either. It's a Chief Scientific Officer routing work to a target-ID team, a safety team, a modality team, a clinical team, and a review panel that argues before anything ships. So we copied that, org chart and all. The loop runs as a graph: a chief-of-staff frames the case, a planner breaks it into axes, specialist scientists run in parallel, and a four-member reviewer panel votes and sends work back when it finds a hole.

This is the direction everyone serious has landed on, which was either reassuring or annoying depending on the hour. Google's AI co-scientist (a multi-agent Gemini system, published in *Nature* this year) runs six named agents under a supervisor in a generate, debate, evolve loop, and ranks competing hypotheses by playing them off each other in an Elo tournament. Edison Scientific's Kosmos coordinates a data-analysis agent and a literature agent through a shared world model, and cites every statement in its report back to code or a paper. Sakana's "AI Scientist" closes the whole loop, idea to written paper, though in machine learning rather than biology. Different flavors of the same bet: a coalition of narrow agents that argue with each other, not one model monologuing into the void.

## The hypothesis is the science, and it keeps changing

I underestimated this part the most. Before you can rank anything, something has to generate the hypotheses worth ranking, and a therapeutic hypothesis isn't a gene. It's a gene in a context: target, disease, modality, mechanism, patient group. "B7-H3, as an ADC, in lung adenocarcinoma, exploiting stromal overexpression" is one hypothesis. The same target as a small molecule is a completely different one with a completely different evidence burden.

And the mechanism story isn't fixed at the start. It develops as the model learns, which honestly was the coolest part to watch. Early on, "PMEL is a good target" is a vague bet. As the agents pull in single-cell specificity, normal-tissue expression, and the tebentafusp precedent, that bet sharpens into something specific: an HLA-agnostic approach against the extracellular domain, exploiting expression that's restricted to malignant cells. You don't hand the system a mechanism. It builds one, and refines it every time new evidence lands. The experiments worth running next are exactly the ones that would sharpen or break the current version of that story.

And here's the part that made "propose an experiment" stop being hand-wavy: those experiments are real tool calls, not vibes. The whole system runs on Harvard's ToolUniverse, roughly 2,600 callable scientific tools, and that's the substrate everything else sits on. Every agent, every axis, every experiment the panel proposes bottoms out in a real tool it can actually invoke. The six axes we score a target on map onto that catalog almost cleanly, so the agents don't generate hypotheses and then gesture at what someone should go run. Each proposed experiment is a specific tool the system can call, or discover it hasn't called yet, which turns "what should we check next" into a concrete pick from a real menu instead of a paragraph of wishful thinking. Which data tells you anything at all depends entirely on the disease and the modality. Single-cell specificity is everything for an ADC in a solid tumor and almost irrelevant for a systemic enzyme replacement. The disease isn't a label on the query. It decides which experiments are even worth proposing.

## Provenance is a control layer, not an audit trail

Here's what I keep relearning about multi-agent systems: left alone, they drift. One agent's low-confidence guess becomes the next agent's cited premise. A missing record gets rounded up to a soft yes. The loop keeps going until something plausible falls out, and plausible is exactly the trap. A bigger prompt does not fix this. What fixes it is a layer sitting between the agents that decides what evidence is allowed to move forward, which agent runs next, and when the loop is allowed to stop.

That layer runs on provenance. Every claim gets typed by where it came from and how sure it is, and those types are the signals the orchestration reads, not decoration for the report. A claim from live computation, a deferred one, and a genuinely empty one are treated differently downstream. An absent record can't be laundered into support by the next agent, because the type travels with the claim. The reviewer panel doesn't vote on prose, it inspects the provenance of each axis, and a thin or deferred axis is what triggers a re-route. The loop stops when the gaps that remain are gaps of fact, not gaps of effort, and synthesis reports those as conditions instead of hiding them.

Because degradation is itself a provenance state, it can't hide either. When a real experiment isn't available and the system falls back, that step gets stamped as a stub in the trace. The control layer sees the stub, refuses to count it as evidence, and the report says so out loud instead of quietly sweeping it under the rug.

You can watch this on a real run. I asked it to assess PMEL (gp100) in melanoma. Five divisions ran in parallel, the reviewer panel flagged a gap, the re-route fired once to a literature synthesizer, and synthesis produced a conditional go.

Here is what came back, axis by axis, with each result tagged by where the evidence came from:

**Right target** — *live, strong.* Queried the TCGA melanoma cohort for PMEL expression.

**Right tissue** — *deferred.* Single-cell specificity, still awaiting an executor to run it.

**Right safety** — *live, strong.* 22 expression records, 13 cancer and 9 normal. And separately, FAERS queried for tebentafusp adverse events.

**Right patient** — *not-run, absent.* The trial finder returned "no studies found."

The verdict was conditional go, medium confidence, and it was conditional precisely because the specificity axis was deferred and the trial axis came back empty. A weaker system rounds that up to a confident yes and moves on. Ours makes the gap a line in the report. The blanks in that table are the whole point, and I'll come back to why.

## Comparing two targets beats scoring them

The dossier tells you about one target. The other half of the system, the arena, is where targets actually compete. The one rule I'm proudest of: no agent is ever allowed to emit a number.

Absolute scores from a language model drift and don't hold their meaning across contexts. Ask it to rate PMEL a 7 and you have learned nothing. But "which of these two is better on this one axis" is a question the model answers reliably. So every judgment is a pairwise, per-axis comparison with a typed verdict: A better, B better, tie, incomparable, or not enough evidence. Six axis judges run at once on each pair. We swap the order of the two targets to kill position bias, and we make confidence explicit so a shaky call can't sneak through dressed as a decisive one.

These run on ten real melanoma targets built from live tool calls. The results form a Pareto front, and the aggregation is deliberately strict: one target only beats another if it wins on at least one axis, loses on none, and leaves nothing unresolved. Everything else gets labeled a tradeoff. That label isn't a failure, it's a pointer to where the next experiment should go.

We reached for a Pareto front because the evaluation for target prioritization just isn't there yet. A front stays customizable, which is the point: a safety-first team and a speed-to-clinic team look at the same front and legitimately pick different targets off it. A single collapsed score pretends there's one right weighting of safety against competition against clinical evidence, and there just isn't.

But novel targets hit a wall, and this is the part that keeps me honest. There's no good ground truth. As Pun and colleagues put it in their 2026 *Nature Reviews Drug Discovery* review, a target is only fully validated once a drug based on it gets approved. The only honest label is temporal and clinical. You'd have to reconstruct the timeline, run the validation, develop the drug, and test it. Benchmarks built on historical approvals lean toward already-drugged target classes and can't reward a correct call on something nobody has tried. So when I say the arena "works," I have to be careful. We can show it enriches for targets that did reach the clinic, but that's a retrospective proxy, not proof it prioritizes the genuinely novel ones. Nobody's metric is, yet. Saying that out loud is part of the point.

## How it stacks up

Two strong reference points already exist, and neither is a strawman I set up to knock down.

The closest paper is Adaszewski and Schindler from Roche (medRxiv, late 2025), prioritizing Alzheimer's targets across six criteria that map almost one-to-one onto ours. They'd already made both bets I was proud of: pairwise comparison, which they show beats pointwise scoring on five of six criteria, and a Pareto frame. So my difference isn't "we do pairwise" or "we thought of Pareto." It's the two moves they don't make. They collapse the front to a single ideal point to force a total ranking, and they stop at a static list. We keep the front partial and close the loop by sending the ties out to a real experiment. The other reference, Claude Science, shares our instinct that a reviewer agent should audit claims, but it does pointwise synthesis per query with no tournament and no loop that breaks a tie by going and getting new evidence.

Which is a humbling thing to learn on a weekend project. The field already converged on the same first instincts I had over pizza, and the interesting work is in the two or three degrees where it hasn't.

## What I actually came away believing

The bottleneck in early drug discovery isn't the biology models. It's the information collection and the decision-making. We have remarkable in-silico tools. What's missing is the connective tissue nobody posts about: gathering the right evidence, knowing it's the right evidence, aggregating it without lying to yourself, and making a decision you can defend.

Two things I want to finish, and both point at those stub nodes in the trace.

The first is telling missingness apart from genuine absence. The little logic layer we started is worth finishing, and its real job isn't symbolic rules for their own sake. It's one distinction: we haven't looked yet, versus we looked and there's genuinely nothing there. Those produce identical-looking blanks, and a model will read either as a soft signal, but they mean opposite things. A blank because a query failed is a gap to fill. A real absence, where nobody has ever run this target in a trial, is itself a finding, and often the most important one, since untested is where novelty hides. A deterministic, replayable rule can tell which blank you're looking at instead of leaving a model to guess.

The second is planning under a budget, which matters more the further downhill you go. At the triage stage we built for, the budget is compute and API calls, so it's cheap. What makes it matter is everything below it. A database query is basically free and a structural prediction costs real compute, but a lead-optimization campaign, a tox study, or a Phase I trial each cost orders of magnitude more and can't be undone once started. A cheap wrong call at triage becomes a hundred-million-dollar wrong call three years later. Same mistake, a thousand times the price. The value of spending your next experiment well compounds the deeper the same logic reaches into development, and I want budget to be a first-class part of that plan the whole way down: spend the next experiment, cheap or expensive, where it most changes the decision, and only while it's worth it. That, more than a bigger model, is where I want to spend my time.

## What's next

There's an obvious next step, and it's the one I've been avoiding because it's harder than shipping another feature. So far I've argued that our two or three degrees of difference matter. I haven't shown they produce better science. The only honest way to test that is to put the runs side by side against the two systems I keep citing and read them like a reviewer would.

So that's the follow-up, and it runs on two tracks. The first is quantitative. I'm going to take the same targets through Claude Science and reconstruct the Adaszewski and Schindler Alzheimer's setup, then measure all three head to head on the retrospective proxies I described above: does each one enrich for targets that actually reached the clinic, and by how much.

The second track is qualitative, and it's the one I'm more curious about. Numbers tell you which system ranks better. They don't tell you whether it ranked better for a reason a scientist would actually sign off on. So I'm going to read the hypothesis-generation process by hand, run by run, and ask whether the hypothesis each system lands on makes biological sense and whether the experiments it wants to run next are the ones a real target-ID team would actually run. A pointwise system and a looped one can reach the same verdict for completely different reasons, and the reasons are the whole game. Where does closing the loop sharpen the hypothesis, and where does it just add noise?

---

*The full system is open source — code, the no-install interactive console, and the recorded runs behind every screenshot: **[github.com/jackysiupuichung/virtual-biotech-scientist](https://github.com/jackysiupuichung/virtual-biotech-scientist)**.*

*A weekend build with friends, pizza, and beer, inspired by Future Bio's "AI Scientists" in London. Built on Harvard's ToolUniverse for the tool layer and Stanford's Virtual Biotech (Zhang et al., 2026) for the org structure. Stanford's Biomni (Huang et al., 2025) is another biomedical agent in the same space, one of the systems worth comparing against.*

*Referenced: Pun et al., "Target identification and assessment in the era of AI," Nat. Rev. Drug Discov., 2026. Google, "Accelerating scientific discovery with Co-Scientist," Nature, 2026. Edison Scientific, "Kosmos," arXiv:2511.02824. Sakana AI, "The AI Scientist," arXiv:2408.06292. Adaszewski and Schindler, medRxiv, 2025. Segall, Curr. Pharm. Des., 2012. Huang et al., "Biomni," bioRxiv 2025.05.30.656746. Anthropic, "Claude Science," 2026.*
