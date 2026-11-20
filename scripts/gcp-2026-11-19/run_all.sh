#!/usr/bin/env bash
# GAMST-HF run on one L4. GPU phases are sequential (one 24 GB card); API arms run beside them.
set -euo pipefail
export HF_ROOT=/srv/hf SA_VIDEOS=/srv/data/streamarena/videos SA_SRC=/srv/StreamArena GAMST_SRC=/srv/gamst
export GOOGLE_CLOUD_PROJECT=optimum-zone PYTHONUNBUFFERED=1
PY=/srv/venv-vllm/bin/python
B=/srv/bench/scripts/gcp-2026-11-19
M=/srv/models
# 8B BF16 + 128-image profiling leaves no KV room on a 24 GB L4: the gate uses Qwen's official
# FP8 release and StreamingVLM (no official FP8) is served with vLLM online FP8 weight quantization.
QWEN8=$M/Qwen3-VL-8B-Instruct-FP8@9cdc6310a8cb770ce18efaf4e9935334512aee45
QWEN3B=$M/Qwen2.5-VL-3B-Instruct@66285546d2b821cf421d4f5eb2576359d3770cd3
SVLM=$M/StreamingVLM@7ac1cef46d20432053a9814838760318cb26b348
cd $HF_ROOT
phase() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a $HF_ROOT/phases.log; }

serve() {  # serve MODEL_DIR NAME [extra vllm args]
  local model=$1 name=$2; shift 2
  pkill -f "vllm serve" || true; sleep 5
  nohup /srv/venv-vllm/bin/vllm serve "$model" --served-model-name "$name" --host 127.0.0.1 --port 8080 \
    --max-model-len 32768 --gpu-memory-utilization 0.92 --max-num-seqs 2 --kv-cache-dtype fp8 \
    --max-num-batched-tokens 8192 --mm-processor-kwargs '{"max_pixels": 200704}' \
    --limit-mm-per-prompt '{"image":130,"video":0}' --seed 0 "$@" > "$HF_ROOT/vllm-$name.log" 2>&1 &
  for i in $(seq 1 120); do curl -sf 127.0.0.1:8080/v1/models >/dev/null && return 0; sleep 5; done
  echo "vllm $name failed"; tail -30 "$HF_ROOT/vllm-$name.log"; exit 1
}

step=${1:-all}
if [[ $step == all || $step == prep ]]; then
  phase prep; bash $B/fetch_videos.sh; $PY $B/hf_bench.py prep
fi
if [[ $step == all || $step == gate ]]; then
  phase "gate Qwen3-VL-8B-FP8"; serve $QWEN8 Qwen3-VL-8B-Instruct-FP8
  $PY $B/hf_bench.py gate
  $PY $B/hf_bench.py judge --gates
  $PY $B/hf_bench.py plugin_episodes
fi
if [[ $step == all || $step == arms ]]; then
  phase "api arms + cpu plugins in background"
  ( $PY $B/hf_bench.py arm strong > arm_strong.log 2>&1; \
    $PY $B/hf_bench.py arm strong_videoonly > arm_strong_videoonly.log 2>&1 ) &
  ( $PY $B/hf_bench.py arm gemini_live > arm_gemini_live.log 2>&1 ) &
  ( $PY $B/modality_signals.py plugin_episodes.jsonl modality_signals.jsonl > signals.log 2>&1 ) &
  phase "qwen_small Qwen2.5-VL-3B"; serve $QWEN3B Qwen2.5-VL-3B-Instruct
  $PY $B/hf_bench.py arm qwen_small
  phase "streamingvlm QA (vLLM, online FP8)"; serve $SVLM StreamingVLM --quantization fp8
  $PY $B/hf_bench.py arm streamingvlm
  pkill -f "vllm serve" || true; sleep 5
  phase "streamingvlm native state"
  (cd /srv/streaming-vlm && PYTHONPATH=/srv/streaming-vlm /srv/venv-svlm/bin/python $B/streamingvlm_state.py \
      $HF_ROOT/plugin_episodes.jsonl $HF_ROOT/streamingvlm_state.jsonl $SVLM > $HF_ROOT/svlm_state.log 2>&1)
  wait
  phase "gamst arms"
  ( $PY $B/hf_bench.py arm gamst_nomedia > arm_gamst_nomedia.log 2>&1 ) &
  $PY $B/hf_bench.py arm gamst
  wait
fi
if [[ $step == all || $step == judge ]]; then
  phase judge; $PY $B/hf_bench.py judge qwen_small,streamingvlm,gemini_live,strong,strong_videoonly,gamst,gamst_nomedia
fi
phase done
