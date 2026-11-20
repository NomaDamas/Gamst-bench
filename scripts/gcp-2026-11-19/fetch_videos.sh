#!/usr/bin/env bash
# Fetch only the StreamArena tars referenced by candidates.jsonl (pinned dataset revision) and keep the mp4.
set -euo pipefail
REV=gs://gamst-bench-datasets-optimum-zone/datasets/streamarena/2960c360deba57b717a17ab66a3ae80f5358a6a3
OUT=/srv/data/streamarena/videos
mkdir -p "$OUT" /srv/data/tmp
python3 -c "import json;print('\n'.join(sorted({json.loads(l)['video_id'] for l in open('/srv/hf/candidates.jsonl')})))" \
  | xargs -P 8 -I{} bash -c '
    v="$1"; [ -s "'"$OUT"'/$v/$v.mp4" ] && exit 0
    gcloud storage cat "'"$REV"'/videos/$v.tar" | tar -x -C "'"$OUT"'" -- "$v/$v.mp4"
    echo "got $v"' _ {}
gcloud storage cp -q "$REV/videos/videos_manifest.jsonl" /srv/data/streamarena/ || true
echo FETCH_DONE
