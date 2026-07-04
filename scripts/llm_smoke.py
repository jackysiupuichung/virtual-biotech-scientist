"""Smoke-test an LLM backend end-to-end.

    uv run python scripts/llm_smoke.py                 # uses VBIO_BACKEND (default: local)
    uv run python scripts/llm_smoke.py --backend local # Ollama, free
    uv run python scripts/llm_smoke.py --backend llama  # university llama.cpp server
    uv run python scripts/llm_smoke.py --backend qwen   # hosted Qwen API (needs QWEN_API_KEY)

Sends one prompt and prints the reply, so you can confirm a backend is reachable
before pointing the agents at it.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm import get_backend

PROMPT = "In one sentence, what is a drug target? Answer plainly."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "local", "llama", "qwen"],
        help="which LLM method to hit (default: auto -> VBIO_BACKEND)",
    )
    ap.add_argument("--prompt", default=PROMPT)
    args = ap.parse_args()

    cfg = get_backend(args.backend)
    print(f"backend={cfg.method}  model={cfg.model}  url={cfg.base_url}", file=sys.stderr)

    import httpx

    try:
        reply = cfg.client().chat(
            [{"role": "user", "content": args.prompt}], max_tokens=200
        )
    except httpx.ConnectError:
        print(
            f"could not reach {cfg.base_url} — is the {cfg.method} server running?\n"
            f"  local: run `uv run python scripts/serve_local.py` in another terminal\n"
            f"  llama: check VBIO_LLAMA_BASE_URL points at the campus llama-server\n"
            f"  qwen : check VBIO_QWEN_BASE_URL / QWEN_API_KEY",
            file=sys.stderr,
        )
        return 1
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
