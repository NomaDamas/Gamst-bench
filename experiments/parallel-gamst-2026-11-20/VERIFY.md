# 모델별 실제 가중치 검증 (단독 실행)

## 측정 조건
- VM `gamst-par`, RTX PRO 6000 Blackwell 96GB
- 입력: StreamArena 실제 클립 앞 60초 `sa60.mp4` (888x480, 24fps, 음성 포함)
  - `run_crew.py --only <모델> --keep-servers`로 실행
  - 미디어는 실시간 속도(1배)로 공급
- 같은 시각에 LLM 서버 2개(Qwen3.5-9B, jev)가 GPU에 떠 있었습니다.
- 가중치 sha256은 `WEIGHTS.md`에 있습니다. GAMST 어댑터가 로드할 때 다시 검사합니다.

## 지표 정의
- **드롭**: 모델이 따라가지 못해 건너뛴 입력의 비율. `latest` 모드는 최신 프레임만 처리하므로, 모델이 느리면 드롭이 생깁니다.
- **계산**: 입력 1개를 처리하는 평균 시간(ms)
- **p95 지연**: 프레임이 링에 올라온 시점부터 결과가 나올 때까지(ms)
- **GPU 최대**: `nvidia-smi`에서 잰 해당 프로세스의 최대 메모리(MiB)

## 결과

| 모델 (어댑터 프로필) | 결과 | 계산 | p95 지연 | 드롭 | GPU 최대 | 메모 |
|---|---|---|---|---|---|---|
| RF-DETR Large (`rfdetr.large`) | ✅ | 7.9ms | 9.9ms | 0.4% | 910 | 237초 클립 전체, 24fps 실시간 |
| YOLOE-26x-seg + MobileCLIP2-B (`yoloe.local`, 텍스트 프롬프트 8개) | ✅ | 12.0ms | 16.9ms | 0.5% | 1,710 | 파라미터 상한을 80M→160M으로 올림 |
| MediaPipe Pose heavy (`mediapipe.body.video`, CPU) | ✅ | 32.3ms | 91.6ms | 8.3% | 0 | CPU 처리라 24fps에서 약 8% 드롭 |
| MediaPipe Hand (`mediapipe.hand.video`, CPU) | ✅ | 9.8ms | 15.6ms | 0% | 0 | |
| MediaPipe Face (`mediapipe.face.video`, CPU) | ✅ | 5.7ms | 10.6ms | 0% | 0 | |
| CED-Base (`ced.onnx`, CPU 4스레드) | ✅ | 4.0ms/100ms 블록 | 39.7ms | 0% | 0 | 저자 PyTorch 모델과 비교: 상위 2개 라벨 같음, 최대 차이 0.031 |
| TEN-VAD (`ten_vad.native`) | ✅ | 0.27ms/32ms 블록 | 0.31ms | 0% | 0 | `libc++1` 설치 후 동작 |
| Nemotron-3-Diarization (`nemotron3.diarization`) | ✅ | 1.5ms/80ms 블록 | 13.8ms | 0% | 1,100 | |
| Qwen3.5-9B 상태 생성 (`streamingvlm.local`) | ⚠️ 재측정 중 | 330ms/프레임(호출당 약 2.6초) | 5.4초 | 20% | (서버) | 8프레임/2초로는 실시간을 넘음 → 6프레임/3초로 조정 |
| SAM 3.1 (`sam3.1.video`) | 🔁 재측정 중 | | | | 8,756 | 체크포인트가 16-object multiplex 구조라 어댑터 수정. 8GB 예산 초과 → 12GB |
| Video Depth Anything Large (`video_depth_anything.large`, fp16) | 🔁 재측정 중 | 99ms | 129ms | 57% | 6,698 | 약 10fps. xformers FA 커널이 Blackwell에서 실패해 제거 |
| FactorizePhys (`factorizephys.local`) | 🔁 재측정 중 | | | | | 공식 학습기처럼 strict=False 로드(FSAM 가중치만 미사용) |
| Qwen3-ASR-1.7B (`qwen3.asr`, vLLM 0.14) | 🔁 재측정 중 | | | | | `max_model_len` 기본 64k로는 KV가 모자라 8192로 설정 |

## 공식 결과와 비교
- 끝난 것: CED (위 표)
- 남은 것: RF-DETR / YOLOE / SAM / VDA / ASR
  - 같은 프레임을 공식 API로 직접 돌린 결과와 어댑터 출력을 비교해야 합니다.
  - 아직 하지 않았습니다.
