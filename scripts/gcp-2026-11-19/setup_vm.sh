#!/usr/bin/env bash
# Fresh L4 VM setup for the GAMST-HF run. Every model/code revision is pinned.
set -euxo pipefail
sudo mkdir -p /srv && sudo chown "$USER" /srv
cd /srv
command -v ffmpeg || { sudo apt-get -o DPkg::Lock::Timeout=900 update -qq && sudo apt-get -o DPkg::Lock::Timeout=900 install -y -qq ffmpeg >/dev/null; }
command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# --- pinned sources
[ -d streaming-vlm ] || git clone -q https://github.com/mit-han-lab/streaming-vlm
git -C streaming-vlm checkout -q a940d8cbfa14eefe651b7f4adeb81825c28cc6c6
[ -d StreamArena ] || git clone -q https://github.com/JIA-Lab-research/StreamArena
git -C StreamArena checkout -q ec0325b9552b045c2e53afbf425315ce867313ee

# --- vLLM + runner env (Qwen3-VL-8B gate, Qwen2.5-VL-3B, StreamingVLM QA arm, Gemini clients)
[ -d venv-vllm ] || uv venv -q -p 3.12 venv-vllm
VIRTUAL_ENV=/srv/venv-vllm uv pip install -q vllm==0.11.0 google-genai numpy huggingface_hub hf_transfer

# --- upstream StreamingVLM inference env (scripts/env_infer.sh, flash-attn wheel per upstream)
[ -d venv-svlm ] || uv venv -q -p 3.11 venv-svlm
grep -v -e '^block_sparse_attn' -e '^flash_attn' streaming-vlm/infer_requirements.txt > /tmp/svlm-req.txt
VIRTUAL_ENV=/srv/venv-svlm uv pip install -q -r /tmp/svlm-req.txt
VIRTUAL_ENV=/srv/venv-svlm uv pip install -q \
  "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.7cxx11abiTRUE-cp311-cp311-linux_x86_64.whl"
VIRTUAL_ENV=/srv/venv-svlm uv pip install -q -e streaming-vlm/streaming_vlm/livecc_utils/

# --- pinned weights
export HF_HUB_ENABLE_HF_TRANSFER=1
dl() { /srv/venv-vllm/bin/hf download "$1" --revision "$2" --local-dir "/srv/models/$(basename "$1")@$2" >/dev/null; }
dl Qwen/Qwen3-VL-8B-Instruct 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b &
dl Qwen/Qwen2.5-VL-3B-Instruct 66285546d2b821cf421d4f5eb2576359d3770cd3 &
dl mit-han-lab/StreamingVLM 7ac1cef46d20432053a9814838760318cb26b348 &
wait
echo SETUP_DONE
