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
| Qwen3.5-9B 상태 생성 (`streamingvlm.local`) | ⚠️ | 412ms/frame 평균 | 4.86s | 2.5% | 서버 | JSON schema로 정상 출력. 6프레임/3초 cadence에서 60초 단독 run 완료; 호출 지연은 실시간보다 큼 |
| SAM 3.1 (`sam3.1.video`) | ❌ | | | 64% | 12,902 | 공식 16-object multiplex 구조로 로드·propagation은 시작되나 `vision_feat` shape `[5184,0,256]` tracker 오류 반복. Blackwell에서 실제 adapter 검증 실패 |
| Video Depth Anything Large (`video_depth_anything.large`, fp16) | ⚠️ | 89.7ms | 128.7ms | 53.5% | 7,858 | 60초 run 종료. 공식 upstream wide-frame handling 적용. 약 10fps라 1배 실시간 전체 프레임 처리는 불가 |
| FactorizePhys (`factorizephys.local`) | ⚠️ | | | 0% | 1,104 | strict=False 공식 inference graph와 checkpoint는 로드. Haar face detection이 실제 클립에서 충분한 얼굴 window를 만들지 못해 pulse output 확정 전 |
| Qwen3-ASR-1.7B (`qwen3.asr`, vLLM 0.14) | ✅ | 34.4ms/20ms block | 133.9ms | 0% | 7,844 | max_model_len=8192, vLLM share 0.07 단독 run. 전체 stack에서는 KV 여유 부족해 추가 budget 조정 필요 |

## 공식 결과와 비교
- 끝난 것: CED (위 표)
- 남은 것: RF-DETR / YOLOE / SAM / VDA / ASR
  - 같은 프레임을 공식 API로 직접 돌린 결과와 어댑터 출력을 비교해야 합니다.
  - 아직 하지 않았습니다.
