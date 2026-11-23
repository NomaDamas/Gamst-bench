#!/usr/bin/env bash
# usage: run_streamarena_arm.sh <out_dir> <policy> <video_ids_csv> <qtypes_csv>
# Native StreamMind driver (pinned) + GAMST extension agent on the shared Qwen3-VL-8B server.
set -euo pipefail
OUT=$1; POLICY=$2; VIDEOS=$3; QTYPES=$4
mkdir -p "$OUT"
export PYTHONPATH=/srv/gamst-bench-ext:/srv/gamst:/srv/benchmarks/streamarena:/srv/benchmarks/streamarena/method/streammind
export GAMST_EXTENSION_VLM_URL=http://127.0.0.1:8080/v1 GAMST_EXTENSION_MODEL=Qwen/Qwen3-VL-8B-Instruct
export GAMST_EXTENSION_POLICY=$POLICY GAMST_EXTENSION_SEMANTIC_INTERVAL_MS=5000 GAMST_EXTENSION_COOLDOWN_MS=1000
export GAMST_EXTENSION_CHANGE_ENTER=0.08 GAMST_EXTENSION_CHANGE_EXIT=0.03 GAMST_EXTENSION_EVIDENCE_CLASS=measured
export GAMST_EXTENSION_SIDECAR=$OUT/gamst-calls.jsonl
cd /srv/benchmarks/streamarena/method/streammind
start=$(date +%s)
rc=0
/srv/venv-streamarena/bin/python run_streammind.py \
  --agent gamst_bench.extensions.streamarena_agent:GamstStreamArenaAgent \
  --dataset /srv/data/streamarena --language en \
  --video-dir /srv/data/streamarena/videos \
  --videos "$VIDEOS" --qtypes "$QTYPES" \
  --out "$OUT/records.jsonl" --fps 2 --disable-audio > "$OUT/run.log" 2>&1 || rc=$?
echo "{\"policy\":\"$POLICY\",\"videos\":\"$VIDEOS\",\"qtypes\":\"$QTYPES\",\"exit\":$rc,\"wall_s\":$(( $(date +%s)-start ))}" > "$OUT/status.json"
