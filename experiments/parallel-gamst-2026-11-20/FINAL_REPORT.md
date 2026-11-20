# parallel GAMST experiment 최종 중간 보고서

## 판정

실험 인프라와 MOT17 평가, 실제 가중치 단독 검증은 완료했습니다. 그러나 **모든 요청 벤치마크가 완료되기 전에는 최종 성공 보고로 판정하지 않습니다.** 현재 RepCount 전체 151개 평가가 실행 중입니다.

## 완료된 평가

### MOT17

실제 RF-DETR Large 결과를 GAMST RiskField와 Watch로 연결하고, B/C arms를 실행했습니다.

| Sequence | GAMST RiskField | B | C-local | C-Gemini |
|---|---:|---:|---:|---:|
| MOT17-09 precision/recall | 0.649/0.963 | 0.703/0.712 | 0.687/0.721 | 0.649/0.963 |
| MOT17-04 precision/recall | 0.742/0.972 | 0.782/0.936 | 0.742/0.972 | 0.742/0.972 |

상세: `MOT17_RESULTS.md`.

### MCD-rPPG

40개 실제 MCD-rPPG 영상:

- MediaPipe face + POS: MAE 19.09 bpm, ±5 bpm 45%, ±10 bpm 57.5%
- 1Hz: MAE 86.06 bpm, ±5 bpm 0%
- before/after 방향 일치: 14/20

### StreamArena

88개 admission clip, judge는 `gemini-3.8-flash`입니다. Gemini 3.1 Pro는 재호출하지 않았습니다.

| Arm | Correct |
|---|---:|
| B: Qwen3.5-9B sliding window | 7/88 |
| C-local: GAMST Context + Qwen3.5-9B | 0/88 |
| C-Gemini: GAMST Context + Gemini 3.8 Flash | 3/88 |

A의 기존 Gemini 3.1 Pro 결과와 judge harness가 다르므로 직접 승패 비교하지 않습니다.

## 실제 가중치 검증

성공: RF-DETR Large, YOLOE-26x, MediaPipe pose/hand/face, CED-Base, TEN-VAD, Nemotron diarization, Qwen3-ASR.

제한/실패:

- SAM 3.1: 공식 16-object multiplex 구조로 로드되지만 실제 tracker에서 `vision_feat=[5184,0,256]` 오류.
- VDA-L: 동시 실행에서 53.5% drop.
- FactorizePhys: checkpoint는 로드됐지만 Haar face window 부족으로 pulse 미확정.
- semantic VLM: JSON schema 출력은 정상이나 동시 실행 p95 지연이 12.2초까지 증가.
- ASR: solo는 동작하지만 full shared stack에서 KV cache 부족.

상세: `VERIFY.md`, `PARALLEL_SMOKE.md`.

## 아직 실행 중

- RepCountA test 151개 pose counting 결과
- 완료 후 shard JSONL 병합, MAE/OBO 계산, 결과 문서 추가

## 종료 조건

RepCount 전체 결과를 기록한 뒤:

1. `RESUME.md`와 `HANDOFF.md` 갱신
2. demo 결과 기록
3. VM 정지
4. PR 상태 확인 및 merge 준비
