# Setup — install & run from the get-go

Two layers to stand up: **ToolUniverse** (the evidence/tool layer, pip + MCP) and
**Claude Science** (the desktop workbench you run the agents inside). Both are wired
so a new contributor can go live as soon as the application code lands.

> **Repo status:** docs + scaffolding today — no application code (`arena/`,
> `skills/`) has landed yet. This page sets up the environment so you can start
> building; the runnable demos below arrive with the code.

## 0. Fast path (no keys)

```bash
bash scripts/setup.sh            # venv + package + uv (for uvx); add --tools for ToolUniverse SDK
. .venv/bin/activate
python -c "import scanpy, anndata, numpy, pandas; print('deps OK')"   # verify the env
```

Once the code lands, the offline demos (arena Pareto/Elo board, CSO spine) and their
tests run here with **no keys**.

## 1. ToolUniverse (evidence/tool layer)

[ToolUniverse](https://github.com/mims-harvard/ToolUniverse) (Zitnik Lab, Harvard)
exposes **1000+ scientific tools, datasets, and models over MCP** — including the
databases this project uses (Open Targets, CELLxGENE, TCGA/GDC, openFDA,
ClinicalTrials.gov) and a **Boltz-2** backend for the arena's `run_experiment`.

**Install (Python ≥3.10):**
```bash
uv pip install tooluniverse       # or: pip install tooluniverse  (installs the `tu` CLI + SDK)
```

**Run as an MCP server** — two ways, both already wired here:

- **Claude Code plugin (recommended):**
  ```bash
  claude plugin marketplace add mims-harvard/ToolUniverse
  claude plugin install tooluniverse@tooluniverse   # auto-starts via `uvx tooluniverse`
  claude plugin list                                 # expect: tooluniverse (enabled)
  ```
- **Project `.mcp.json` (checked in):** launches `uvx --refresh tooluniverse` for any
  MCP client that reads it. Nothing else to configure.

**Keep context small (important).** ToolUniverse ships 1000+ tool schemas; loading
them all blows the context window. Expose a subset with compact mode / tool filters:
```bash
tooluniverse-smcp --compact-mode
tooluniverse-smcp --include-tools OpenTargets_get_associated_diseases,Boltz2_predict_binding_affinity
```
This matches the design's guidance in [DESIGN.md §5](../design/DESIGN.md) — expose a handful of
discovery tools, not the full 580+/1000+ catalogue.

**Keys:** none required for the public databases. A few tools are key-gated and stay
disabled when unset (`NCBI_API_KEY`, `NVIDIA_API_KEY` for hosted Boltz-2,
`ONCOKB_API_TOKEN`) — see [`.env.example`](../../.env.example).

**Boltz-2 for the arena:** ToolUniverse's Boltz-2 tool is the intended live backend
behind the arena's `run_experiment` interface (see
[ARENA.md §5.1](../design/ARENA.md#51-the-most-informative-action-may-be-an-experiment)). Wiring
it is a planned workstream once the arena code lands.

## 2. Claude Science (the workbench)

[Claude Science](https://claude.com/product/claude-science) is a **desktop app**
(beta, GA for all paid plans — Pro/Max/Team/Enterprise). It is the environment the
agents run inside; there is no pip package or public CLI/SDK — you install the app and
configure Skills/Connectors in it.

**Enable & install:**
1. **Team/Enterprise:** an admin enables it at *Organization settings → Capabilities*
   (Pro/Max users can skip straight to the download).
2. Complete the setup wizard: review role access, configure connectors, authorize
   team resources.
3. Download the app from <https://claude.com/product/claude-science> and sign in with
   your claude.ai account.

**How this repo will map onto it** (once the code lands):
- each planned `skills/*/SKILL.md` → a Claude Science **Skill** (near drop-in);
- external databases → **Connectors** (Anthropic-curated *featured connectors*, plus
  local connectors that run on each member's machine — ToolUniverse's MCP server is one);
- Boltz-2 / Evo 2 / OpenFold3 → **BioNeMo** models on **Modal** GPU;
- the Scientific Reviewer → the built-in **reviewer agent**;
- the arena's ranking result + decision cards → reproducible **artifacts**.

**Funding:** the **AI for Science grant** (up to $30k credits + $2k Modal, deadline
**2026-07-15**) is the intended way to get compute for the live Boltz-2 path.

## 3. What needs keys, at a glance

| To run | Keys |
| --- | --- |
| Offline demos (arena, CSO spine) + tests, once code lands | none |
| ToolUniverse public databases (OT, CELLxGENE, TCGA, openFDA, trials) | none |
| Spine `--live` (LLM agents + arena judge) | one of `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` (or Claude Code CLI) |
| Hosted Boltz-2 via ToolUniverse | `NVIDIA_API_KEY` (optional) |
| Claude Science workbench | a paid claude.ai plan (app sign-in) |

