# Full concurrent smoke 결과

## 조건
- VM `gamst-par`, RTX PRO 6000 96GB
- 실제 StreamArena clip `sa60.mp4`, 60.08초, video+audio
- Qwen3.5-9B와 jev 서버가 동시에 이미 실행 중
- 모든 stack worker를 한 번에 기동
- `--allow-failed-workers`는 실패 worker를 숨기지 않고 나머지 동시 측정을 계속하기 위한 진단 옵션입니다. 순차 폴백이 아닙니다.

## 관측

| worker | 결과 | processed | drop | errors | GPU peak | note |
|---|---:|---:|---:|---:|---:|---|
| semantic Qwen3.5 | ⚠️ | 53 | 56.2% | 0 | server | 동시 GPU 압박에서 호출 p95 12.2s |
| RF-DETR Large | ✅ | 1431 | 0.76% | 0 | 910MiB | 동시 실행에서도 유지 |
| YOLOE-26x | ✅ | 901 | 37.5% | 0 | 1.71GiB | solo 0.5%에서 동시 압박으로 증가 |
| SAM3.1 | ❌ | 159 | 88.9% | 19 | 12.4GiB | 내부 `vision_feat` zero-batch tracker 오류 |
| VDA-L | ✅/⚠️ | 219 | 84.8% | 0 | 7.86GiB | 동시 실행에서 realtime 불가 |
| Pose heavy | ✅ | 1310 | 9.15% | 0 | CPU | |
| Hand | ✅ | 1442 | 0% | 0 | CPU | |
| Face | ✅ | 1442 | 0% | 0 | CPU | |
| FactorizePhys | ⚠️ | 1 | 0% | — | 1.10GiB | face window/pulse output 미확정 |
| Qwen3-ASR | ⚠️ | — | — | — | 9.9GiB | shared KV memory 부족으로 종료 |
| CED-Base | ✅ | 600 | 0% | 0 | CPU | |
| TEN-VAD | ✅ | 1876 | 0% | 0 | CPU | |
| Nemotron diarization | ✅ | 750 | 0% | 0 | 1.10GiB | |

- wall realtime factor: **1.0438** (실패 worker 포함, 전체 clip replay 자체는 약 1배)
- 전체 GPU 사용 peak: 약 78.4GiB 관측
- GPU budget violation: ASR 10,166MiB > 9,500MiB; FactorizePhys 1,104MiB > 1,024MiB

## 결론

- GamstCrew의 핵심 요구(모델별 process, shared frame/audio rings, single clock, 1Hz monitor, concurrent startup)는 실제 smoke에서 동작했습니다.
- "모든 SOTA 모델이 동시에 성공"은 달성하지 못했습니다.
  - SAM3.1: 공식 코드 내부 tracker failure.
  - ASR: shared GPU KV budget failure.
  - FactorizePhys: face/pulse pipeline incomplete.
  - VDA/YOLOE/semantic: 동시 실행에서 drop/latency가 크게 증가.
- 이 결과를 성공으로 포장하지 않습니다. 비용을 발생시키는 상용 대체 API는 사용자에게 별도 승인을 받기 전 사용하지 않습니다.
