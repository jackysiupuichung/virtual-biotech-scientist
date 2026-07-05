# virtual-biotech-cso — running it

A therapeutic-target-assessment orchestrator: it plans divisions, routes each axis
to a **ToolUniverse** tool (pinned or discovered), and has an **LLM agent** fill the
reasoning roles (Chief of Staff, Scientific Reviewer, CSO synthesis). Two live layers:

- **Tools** — ToolUniverse (Open Targets, GWAS Catalog, ClinicalTrials, CellMarker, …).
- **Reasoning** — a pluggable LLM backend (Anthropic / OpenAI-compatible / Gemini /
  Claude CLI). Anything OpenAI-compatible includes a **local GGUF** server.

Two entry points:

| Script | LLM? | Use |
| --- | --- | --- |
| `cso.py`     | no  | deterministic orchestrator — plan + route + render; roles are stubs |
| `harness.py` | yes | the live multi-agent loop — the LLM agent fills the reasoning roles |

For live reasoning you run **`harness.py`**. `cso.py` alone never calls an LLM.

---

## Run fully local with a GGUF model

Everything on your machine: a **local GGUF LLM** (served OpenAI-compatibly) for the
agent, plus ToolUniverse for the tools. No cloud API key, no data leaving the box.

### 1. Serve the GGUF model (OpenAI-compatible)

Any server that exposes the OpenAI `/v1/chat/completions` API works. Two common ones:

**llama.cpp** (`llama-server`):

```bash
# e.g. a Qwen2.5-7B-Instruct GGUF; --jinja enables the chat template, needed for JSON
llama-server -m ./models/qwen2.5-7b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 --port 8080 --jinja -c 8192
# → OpenAI endpoint at http://127.0.0.1:8080/v1
```

**LM Studio**: load the GGUF, start the local server (Developer → Start Server),
default endpoint `http://localhost:1234/v1`. Copy the model id it shows.

> Pick an **instruct** model that can emit JSON — the roles use JSON mode. 7B+ Q4 or
> better is recommended; tiny models often break the structured-output contract.

### 2. Install ToolUniverse (the live tool layer)

```bash
uv sync --extra tools        # installs tooluniverse>=1.0 into the venv
```

This activates the **in-process** tool path: routed axes call ToolUniverse directly,
no MCP server or agent needed. (Embedding discovery `Tool_Finder` also wants ML deps —
`uv sync --extra tools` pulls the base package; the keyword finder works without them.)

**Compact by default.** In-process ToolUniverse loads a *restricted* tool surface —
only the tools the CSO's `tool_router.yaml` maps plus the discovery finders (~10 tools)
— instead of all 2599. This is fast and is the intended posture. To load the full
catalogue (needed only if live discovery must reach tools outside the pinned set):

```bash
export VBIO_TU_FULL=1        # load all 2599 tools instead of the compact ~10
```

### 3. Point the LLM backend at your local server and run

```bash
# --- local GGUF via the OpenAI-compatible runner ---
export OPENAI_BASE_URL="http://127.0.0.1:8080/v1"   # llama.cpp (LM Studio: :1234/v1)
export OPENAI_API_KEY="local"                        # any non-empty string; local server ignores it
export VBIO_MODEL="qwen2.5-7b-instruct"              # the model id your server reports

uv run python skills/virtual-biotech-cso/harness.py \
  --backend openai \
  --live \
  --query "Assess PMEL (gp100) as a therapeutic target in melanoma" \
  --output ./out
```

- `--backend openai` selects the OpenAI-compatible runner (which honours
  `OPENAI_BASE_URL` + `VBIO_MODEL`).
- `--live` executes the routed axes through ToolUniverse (else steps stay stubs).
- `OPENAI_API_KEY` must be **set to something** — the OpenAI SDK requires it even
  though a local server ignores the value.

Artifacts land in `./out/`:

- `report.md` — the target-assessment dossier (evidence table, decision, references)
- `result.json` — machine envelope (briefing, plan, evidence, review, synthesis)
- `trace.jsonl` — the agent execution graph (which role/tool ran, in order)

### One-liner

```bash
OPENAI_BASE_URL=http://127.0.0.1:8080/v1 OPENAI_API_KEY=local VBIO_MODEL=qwen2.5-7b-instruct \
uv run python skills/virtual-biotech-cso/harness.py --backend openai --live \
  --query "Assess PMEL (gp100) as a therapeutic target in melanoma" --output ./out
```

---

## Other backends (for reference)

```bash
# Anthropic (cloud)
ANTHROPIC_API_KEY=sk-ant-... uv run python skills/virtual-biotech-cso/harness.py --live --query "..." --output ./out

# Gemini (Google AI Studio free tier)
GEMINI_API_KEY=... uv run python skills/virtual-biotech-cso/harness.py --backend gemini --live --query "..." --output ./out

# No LLM at all — deterministic, roles stubbed (structure only, honest "not executed")
uv run python skills/virtual-biotech-cso/harness.py --live --query "..." --output ./out
```

`--backend auto` (the default) picks the first available: Anthropic key → OpenAI key
→ Gemini key → local `claude` CLI → stub.

---

## Offline evaluation ground (no live calls)

To review the output shape with **real, captured** ToolUniverse data and no network:

```bash
uv run python skills/virtual-biotech-cso/eval/run_eval.py \
  --fixture skills/virtual-biotech-cso/eval/pmel_melanoma.json \
  --output skills/virtual-biotech-cso/eval/out
```

Replays captured tool outputs for PMEL/gp100 in melanoma → the same three artifacts,
deterministic, no LLM (reasoning roles are stubs).

---

## Status / caveats

- **LLM reasoning**: ✅ works with any backend above (local GGUF, Anthropic, Gemini,
  Claude CLI). Verified end-to-end: a live run planned a 10-axis assessment and filled
  every reasoning role (chief-of-staff, planner, division scientists, reviewer panel).
- **Live tools in-process**: ✅ verified against `tooluniverse` 1.3.1 —
  `tu.run({"name", "arguments"})` returns real Open Targets / GWAS / CellMarker /
  ClinicalTrials data. Loads a compact tool set by default (see above).
- **Discovery** (`find → compose → run` for an *unmapped* axis): partial. In-process
  execution of a *pinned* axis works; the discovery `find`/`compose` step still needs
  the ML deps (`tooluniverse[embedding]`) or an injected executor, else the axis
  returns an honest `tool-descriptor` (deferred), never a fabricated result.
- Nothing is ever fabricated: a missing backend or tool yields an honest stub.
