"""Download a tiny GGUF and serve it locally as an OpenAI-compatible endpoint.

Fully uv-native (no brew, no Ollama): uses ``huggingface-hub`` to fetch a small
quantised model and ``llama_cpp.server`` to expose it at
``http://localhost:8080/v1`` — the same OpenAI wire protocol as the university
llama.cpp server, so the ``local`` backend and ``llama`` backend share code.

    uv run python scripts/serve_local.py           # default: Qwen2.5-0.5B-Instruct Q4
    uv run python scripts/serve_local.py --port 8081

Leave it running in one terminal, then in another:

    uv run python scripts/llm_smoke.py --backend local
"""

from __future__ import annotations

import argparse

# Tiny, fast, CPU-friendly. ~350 MB download; good enough to exercise the pipeline.
DEFAULT_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
DEFAULT_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=DEFAULT_REPO, help="HF repo id with GGUF files")
    ap.add_argument("--file", default=DEFAULT_FILE, help="GGUF filename in the repo")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    from huggingface_hub import hf_hub_download

    print(f"fetching {args.repo}/{args.file} (cached after first run)...")
    model_path = hf_hub_download(repo_id=args.repo, filename=args.file)
    print(f"model: {model_path}")

    # Hand off to llama_cpp's OpenAI-compatible server.
    import sys

    from llama_cpp.server.app import create_app
    from llama_cpp.server.settings import ModelSettings, ServerSettings
    import uvicorn

    server = ServerSettings(host=args.host, port=args.port)
    models = [ModelSettings(model=model_path, model_alias="local")]
    app = create_app(server_settings=server, model_settings=models)

    print(f"serving OpenAI /v1 at http://{args.host}:{args.port}/v1  (model alias: local)")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
