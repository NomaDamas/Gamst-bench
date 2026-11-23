# 가중치 목록 (VM `gamst-par`의 `/srv/models`, 2026-11-20에 sha256 계산)

- "출처"는 공식 위치이며 revision을 고정했습니다.
- `/srv/models` 아래 경로는 **굵은 글씨**로 표시합니다.
- 실제 영상으로 검증한 결과는 `VERIFY.md`에 기록합니다.

| 모델 | 출처 (고정) | 파일 | sha256 |
|---|---|---|---|
| Qwen3.5-9B (스트리밍 VLM, B/C-local 소비자) | HF `Qwen/Qwen3.5-9B@c202236235762e1c871ad0ccb60c8ee5ba337b9a` | **`Qwen3.5-9B@c202236…/`** (snapshot) | HF revision으로 고정 |
| Qwen3.8-27B-FP8 (jev) | HF `Qwen/Qwen3.8-27B-FP8@c3a462cc3d38cf351f3b26cbd763469eeb74ef81` | **`Qwen3.8-27B-FP8@c3a462c…/`** | HF revision으로 고정 |
| Qwen3-ASR-1.7B | HF `Qwen/Qwen3-ASR-1.7B@7278e1e70fe206f11671096ffdd38061171dd6e5` | **`Qwen3-ASR-1.7B@7278e1e…/`** | HF revision으로 고정 |
| SAM 3.1 | HF `facebook/sam3.1@daa63191845a41281374e725f4c9e51c7a824460` (gated, 승인됨) | **`sam3.1@daa6319…/sam3.1_multiplex.pt`** | `0567debeec80ba4ac6369540c6c248025283cb3ff2b92827509e57e2b3541cb6` |
| Video Depth Anything Large | HF `depth-anything/Video-Depth-Anything-Large@7aafbcb5c6af0bac741aad2b6471894fb4761afa` (CC-BY-NC-4.0, 연구용) | **`Video-Depth-Anything-Large@7aafbcb…/video_depth_anything_vitl.pth`** | `43df27c6b396042ba34ff7b798ab279f64d204d2e86d7a373968f8fa36d0e6fa` |
| RF-DETR Large | rfdetr 1.12.1 등록 체크포인트 (Roboflow 배포 MD5 확인) | **`rfdetr/rf-detr-large-2026.pth`** | `0f4e20e19a99c0f8a62b5685f57f6c8b5c371c59081feda6752a0561a79ccf38` |
| YOLOE-26x-seg | ultralytics 릴리스 자산 (8.4.212) | **`yoloe/yoloe-26x-seg.pt`** | `d08d390a08f98195f7c87807839fe4ff93a5491645fef1bc3bf0700efafdd639` |
| MobileCLIP2-B (YOLOE 텍스트 인코더) | ultralytics 릴리스 자산 | **`yoloe/mobileclip2_b.ts`** | `35d7f213e4d75f38514e4656ad3cb91158bd33e3805d8ac349f23b186f66982f` |
| MediaPipe Pose heavy | `storage.googleapis.com/mediapipe-models/.../pose_landmarker_heavy/float16/latest` | **`mediapipe/pose_landmarker_heavy.task`** | `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b` |
| MediaPipe Hand | 같은 저장소 | **`mediapipe/hand_landmarker.task`** | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
| MediaPipe Face | 같은 저장소 | **`mediapipe/face_landmarker.task`** | `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` |
| CED-Base (오디오 이벤트) | HF `mispeech/ced-base@db3e14a8db4c21b56b165261c39649741a900e7f` (Zenodo는 403이라 README의 HF 경로 사용) | **`ced-base/model.onnx`** | `1cb33c4300b6c52ae099a5af72058982e673ec79862855961b8b8c10eeaba74c` |
| | | **`ced-base/model.safetensors`** | `314935693ed1dcef07576ca0c41277c51c642f3847bc5eb03918c5277eb79af9` |
| Nemotron-3-Diarization | HF `nvidia/Nemotron-3-Diarization@52a432672732425e4c19765b9fec9b5810e6f4ba` | **`nemotron3-diar/model.safetensors`** | `c074d86335b3b794f8fa5edc25594558f128bdb3914d27806a3a5a2e44963cb6` (어댑터 고정값과 일치) |
| TalkNet (TalkSet) | TalkNet-ASD `6d68214` `demoTalkNet.py`의 Google Drive ID | **`talknet/pretrain_TalkSet.model`** | `d985ddd07dca08864a28337726f5b7d91b6426bebc7327f0e9b21cf9ff1cc937` |
| FactorizePhys (rPPG) | rPPG-Toolbox `b7500b8` `final_model_release/` | `/srv/src/rPPG-Toolbox/final_model_release/iBVP_FactorizePhys_FSAM_Res.pth` | `21e20ea54498adcf4b4238cc49d407c807df08e2cf8c0e5cf8c6518ab463bf27` |
| | | `UBFC-rPPG_FactorizePhys_FSAM_Res.pth` | `03cb8590e0b1f0fe669534d9708520fed0b20e1fe28e1b57a56a2504b4a246f6` |
| | | `PURE_FactorizePhys_FSAM_Res.pth` | `00352947d39aee1853b5bff00577916876a89a6f81bf8e49216432f1c5bb9bbb` |
| EfficientPhys (기존 어댑터 비교용) | 같은 위치 | `UBFC-rPPG_EfficientPhys.pth` | `219b970e04b3580ee4c063554b7d9fe2a7a3ceb4e9e585980f15ac8313054cd6` |
| TEN-VAD | ten-vad `9a3f4b5` | `/srv/src/ten-vad/lib/Linux/x64/libten_vad.so` | `5abfe6bf6e9a4fcea6b440240f0a9a0f431ab5006e48a4e16465ebe681ffd90f` |
