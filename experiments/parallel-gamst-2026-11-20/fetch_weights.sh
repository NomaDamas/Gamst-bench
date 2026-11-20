#!/bin/bash
# Fetch every model artifact for the parallel run into /srv/models and print sha256.
# Large HF snapshots (Qwen3.5-9B, Qwen3.8-27B-FP8, Qwen3-ASR-1.7B, SAM 3.1, VDA-L) are
# fetched by revision in setup; this script fetches the remaining files.
set -u
M=/srv/models; mkdir -p $M/rfdetr $M/yoloe $M/mediapipe $M/ced $M/talknet $M/nemotron3-diar
get() { [ -s "$2" ] || curl -fsSL --retry 3 -o "$2" "$1" || echo "FAIL $1"; }

# RF-DETR Large (rfdetr==1.12.1 downloads its registered checkpoint into the cwd).
(cd $M/rfdetr && /srv/envs/det/bin/python -c "from rfdetr import RFDETRLarge; RFDETRLarge()" >/dev/null 2>&1)

# YOLOE-26x promptable segmentation + MobileCLIP2-B text encoder (ultralytics release assets).
(cd $M/yoloe && /srv/envs/det/bin/python - <<'PY' >/dev/null 2>&1
from ultralytics.utils.downloads import attempt_download_asset
for name in ("yoloe-26x-seg.pt", "mobileclip2_b.ts"):
    attempt_download_asset(name)
PY
)

# MediaPipe heavy/full landmarkers (Google model cards).
get https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task $M/mediapipe/pose_landmarker_heavy.task
get https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task $M/mediapipe/hand_landmarker.task
get https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task $M/mediapipe/face_landmarker.task

# CED-Base (official Zenodo record linked from RicherMans/CED README at the pinned revision).
get "https://zenodo.org/record/8275347/files/audiotransformer_base_mAP_4999.pt?download=1" $M/ced/audiotransformer_base_mAP_4999.pt

# TalkNet pretrained on TalkSet (official link used by TalkNet-ASD demoTalkNet.py).
[ -s $M/talknet/pretrain_TalkSet.model ] || /srv/envs/torch28/bin/python -m gdown -q --id 1AbN9fCf9IexMxEKXLQY2KYBlb-IhSEea -O $M/talknet/pretrain_TalkSet.model 2>/dev/null || echo "FAIL talknet (gdown)"

# Nemotron-3-Diarization at the adapter's pinned revision.
/srv/venv-vllm34/bin/python - <<'PY' >/dev/null 2>&1 || echo "FAIL nemotron3-diar"
from huggingface_hub import snapshot_download
snapshot_download("nvidia/Nemotron-3-Diarization", revision="52a432672732425e4c19765b9fec9b5810e6f4ba",
                  local_dir="/srv/models/nemotron3-diar", allow_patterns=["config.json", "processor_config.json", "model.safetensors"])
PY

find $M/rfdetr $M/yoloe $M/mediapipe $M/ced $M/talknet $M/nemotron3-diar -maxdepth 1 -type f \
  \( -name '*.pth' -o -name '*.pt' -o -name '*.ts' -o -name '*.task' -o -name '*.model' -o -name '*.safetensors' -o -name '*.json' \) \
  -exec sha256sum {} \; | sort -k2
for f in $M/sam3.1@*/sam3.1_multiplex.pt $M/Video-Depth-Anything-Large@*/video_depth_anything_vitl.pth \
         /srv/src/rPPG-Toolbox/final_model_release/*FactorizePhys* /srv/src/rPPG-Toolbox/final_model_release/*EfficientPhys.pth \
         /srv/src/ten-vad/lib/Linux/x64/libten_vad.so; do sha256sum "$f"; done
echo FETCHDONE
