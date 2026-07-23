#!/usr/bin/env bash
# run_braf_llamacpp.sh — ONE melanoma case study (BRAF) against a locally-held
# llama.cpp server, with ToolUniverse compact mode OFF.
#
# Structure borrowed from graphtarget/scripts/run_qwen3_all_windows_oneserver.sh:
# hold ONE GPU, start ONE llama-server, health-poll it, run the client, tear down
# once via a trap.
#
# Why llama.cpp and not vLLM: vLLM is not installed here, and the only
# vLLM-ready (HF safetensors) checkpoint on this cluster is Qwen2.5-1.5B — the
# 7B exists only as GGUF, which is llama.cpp's native format.
#
# Submit:
#   sbatch scripts/slurm/run_braf_llamacpp.sh
# Or inside an existing allocation:
#   srun --jobid=<ALLOC> bash scripts/slurm/run_braf_llamacpp.sh
#
#SBATCH -J vbio-braf-llamacpp
#SBATCH -o logs/%x.o%j
#SBATCH -p sae
#SBATCH --account=pilot_sae_gpu
#SBATCH -n 8
#SBATCH --cpus-per-gpu=8
#SBATCH --mem-per-cpu=11G
#SBATCH --gres=gpu:1
#SBATCH -t 04:00:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/data/home/bty414/virtual-biotech-scientist}"
cd "${REPO_ROOT}"
unset VIRTUAL_ENV          # a stale outer venv shadows .venv and breaks imports

# Run artifacts live on scratch (large, regenerable — not $HOME quota, not git).
# The repo carries `output`/`logs` as symlinks into scratch; recreate both here
# so a fresh checkout self-heals instead of writing real dirs onto $HOME.
SCRATCH_ROOT="${SCRATCH_ROOT:-/gpfs/scratch/${USER}/virtual-biotech-scientist}"
for d in output logs; do
    mkdir -p "${SCRATCH_ROOT}/${d}"
    # (re)point the repo symlink at scratch unless it already resolves there
    if [[ "$(readlink -f "${d}" 2>/dev/null)" != "${SCRATCH_ROOT}/${d}" ]]; then
        rm -rf "${d}"
        ln -s "${SCRATCH_ROOT}/${d}" "${d}"
    fi
done

# --- the one example -------------------------------------------------------
# BRAF in melanoma: the SETUP.md example query, a shipped arena card, and the
# textbook melanoma driver (V600E -> vemurafenib). Well-known biology means a
# 7B's failures read as failures, not as unfamiliarity.
TARGET="${TARGET:-BRAF}"
DISEASE="${DISEASE:-melanoma}"
QUERY="${QUERY:-Assess ${TARGET} as a therapeutic target in ${DISEASE}}"
OUT_DIR="${OUT_DIR:-output/${TARGET,,}_${DISEASE}_llamacpp_$(date +%Y%m%d-%H%M%S)}"

# --- THE POINT OF THIS RUN: compact mode OFF -------------------------------
# tool_backend.py:_get_tooluniverse() loads only the router's tool subset (12
# tools) unless VBIO_TU_FULL=1, which loads all 2599. Setting it here is what
# makes this the NON-COMPACT run. Measured: 12 tools instant vs 2599 in ~27s.
#
# Expect strain: 2599 schemas is far more than a 7B holds at any CTX_SIZE. That
# strain IS the experiment — the artefact of interest is WHERE it degrades
# (tool selection? planning?), recorded in the trace under ${OUT_DIR}.
export VBIO_TU_FULL=1

# --- model + server --------------------------------------------------------
MODEL_LABEL="${MODEL_LABEL:-Qwen/Qwen2.5-7B-Instruct}"
MODEL_FILE="${MODEL_FILE:-/gpfs/scratch/${USER}/gguf/Qwen2.5-7B-Instruct-Q4_K_M.gguf}"
LLAMA_SERVER="${LLAMA_SERVER:-/gpfs/scratch/${USER}/llama.cpp/build/bin/llama-server}"
N_GPU_LAYERS="${N_GPU_LAYERS:-99}"     # 99 = offload all layers; 7B Q4 is ~4.7GB
CTX_SIZE="${CTX_SIZE:-32768}"          # generous: compact mode is off
PARALLEL="${PARALLEL:-1}"

# Port derived from the job id so concurrent jobs never collide.
if [[ -z "${PORT:-}" ]]; then
    PORT=$(( 18000 + ${SLURM_JOB_ID:-0} % 10000 )); [[ "${PORT}" == 18000 ]] && PORT=8080
fi
SERVER_URL="http://127.0.0.1:${PORT}"

[[ -x "${LLAMA_SERVER}" ]] || { echo "ERROR: llama-server not at ${LLAMA_SERVER}" >&2; exit 1; }
[[ -f "${MODEL_FILE}" ]]   || { echo "ERROR: GGUF not at ${MODEL_FILE}" >&2; exit 1; }
[[ -d .venv ]]             || { echo "ERROR: no .venv — run: CMAKE_BUILD_PARALLEL_LEVEL=4 uv sync --extra tools --extra dev" >&2; exit 1; }

# --- CUDA driver lib -------------------------------------------------------
# llama-server links libcuda.so.1, which exists only on GPU nodes and is not
# always on the default loader path. Lifted from graphtarget's runner.
if command -v module >/dev/null 2>&1; then module load cuda/12.4.0-gcc-12.2.0 || true; fi
LIBCUDA_DIR=""
for d in /usr/lib64 /usr/lib/x86_64-linux-gnu \
         /cm/local/apps/cuda-driver/libs/current/lib64 \
         /opt/nvidia/lib64 /run/nvidia/driver/usr/lib64; do
    [[ -e "${d}/libcuda.so.1" ]] && { LIBCUDA_DIR="${d}"; break; }
done
[[ -z "${LIBCUDA_DIR}" ]] && LIBCUDA_DIR="$(ldconfig -p 2>/dev/null | awk '/libcuda\.so\.1/ {print $NF; exit}' | xargs -r dirname || true)"
[[ -n "${LIBCUDA_DIR}" ]] || { echo "ERROR: libcuda.so.1 not found — are you on a GPU node?" >&2; exit 1; }
export LD_LIBRARY_PATH="${LIBCUDA_DIR}:${LD_LIBRARY_PATH:-}"

# --- start the server ------------------------------------------------------
LOG_FILE="logs/llama_server.braf.${SLURM_JOB_ID:-local}.$(date +%Y%m%d-%H%M%S).log"
echo ">> llama-server on ${SERVER_URL}"
echo "   model : ${MODEL_FILE}"
echo "   ctx   : ${CTX_SIZE}   ngl: ${N_GPU_LAYERS}"
echo "   log   : ${LOG_FILE}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true

# --jinja is REQUIRED: llama-server only honours the chat template with jinja
# templating on. graphtarget lost a full 16-run sweep to coverage=0 because it
# was omitted and Qwen emitted <think> as its first token.
"${LLAMA_SERVER}" \
    -m "${MODEL_FILE}" \
    --host 127.0.0.1 --port "${PORT}" \
    --jinja \
    -ngl "${N_GPU_LAYERS}" -c "${CTX_SIZE}" \
    --parallel "${PARALLEL}" \
    --no-webui \
    > "${LOG_FILE}" 2>&1 &
SERVER_PID=$!

cleanup() {
    if kill -0 "${SERVER_PID}" 2>/dev/null; then
        echo ">> stopping llama-server (pid ${SERVER_PID})"
        kill "${SERVER_PID}" 2>/dev/null || true
        wait "${SERVER_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo ">> waiting for ${SERVER_URL}/health ..."
for i in $(seq 1 300); do
    kill -0 "${SERVER_PID}" 2>/dev/null || { echo "ERROR: server exited early:" >&2; tail -40 "${LOG_FILE}" >&2; exit 1; }
    curl -sf "${SERVER_URL}/health" -o /dev/null && { echo "   ready after ${i}s"; break; }
    sleep 1
done
curl -sf "${SERVER_URL}/health" -o /dev/null || { echo "ERROR: not healthy in 300s:" >&2; tail -40 "${LOG_FILE}" >&2; exit 1; }

# Probe JSON mode before spending a GPU-hour on it. runners.py:198 sends
# response_format={"type":"json_object"}; older llama.cpp builds ignore it
# silently, which surfaces later as unparseable agent output rather than a
# clean error. Warn, don't abort — the harness degrades to a stub honestly.
echo ">> probing json_object support ..."
PROBE=$(curl -sf "${SERVER_URL}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model":"probe","messages":[{"role":"user","content":"Reply with JSON {\"ok\":true}"}],"response_format":{"type":"json_object"},"max_tokens":32}' \
    2>/dev/null | tr -d '\n' || true)
if grep -q '"ok"' <<<"${PROBE}"; then
    echo "   json_object: OK"
else
    echo "   WARNING: json_object probe did not return the expected shape."
    echo "   response: ${PROBE:0:300}"
    echo "   Agent steps may degrade to stubs; check ${OUT_DIR} traces."
fi

# --- point the harness at it ----------------------------------------------
# runners.py:OpenAIRunner already honours OPENAI_BASE_URL, so the existing
# `openai` backend drives llama-server with NO new runner code. The key is
# unused by llama-server, but the OpenAI SDK refuses to construct without one.
export OPENAI_BASE_URL="${SERVER_URL}/v1"
export OPENAI_API_KEY="${OPENAI_API_KEY:-llama-cpp-no-key}"
export VBIO_MODEL="${MODEL_LABEL}"

echo "──────────────────────────────────────────────────────────"
echo ">> ${TARGET} / ${DISEASE}   compact=OFF (VBIO_TU_FULL=1 -> 2599 tools)"
echo "   query : ${QUERY}"
echo "   out   : ${OUT_DIR}"
mkdir -p "${OUT_DIR}"

uv run python skills/virtual-biotech-cso/harness.py \
    --query "${QUERY}" \
    --backend openai \
    --model "${MODEL_LABEL}" \
    --live \
    --out "${OUT_DIR}"

echo ">> done → ${OUT_DIR}"
