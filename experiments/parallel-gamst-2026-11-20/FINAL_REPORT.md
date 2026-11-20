# parallel GAMST experiment 최종 보고서

## 결론

실제 데이터 기반 평가와 full concurrent smoke를 완료했습니다. **모든 SOTA 모델이 동시에 성공한 것은 아닙니다.** SAM 3.1, FactorizePhys, shared-GPU ASR는 실패/미완으로 남겼고, 유료 대체 API는 사용하지 않았습니다.

## 평가 결과

### MOT17 B / C-local / C-Gemini

| Sequence | GAMST RiskField | B | C-local | C-Gemini |
|---|---:|---:|---:|---:|
| MOT17-09 precision/recall | 0.649/0.963 | 0.703/0.712 | 0.687/0.721 | 0.649/0.963 |
| MOT17-04 precision/recall | 0.742/0.972 | 0.782/0.936 | 0.742/0.972 | 0.742/0.972 |

상세: `MOT17_RESULTS.md`. jev는 실제 `create_watch` tool call을 만들었고, 잘못된 subject 생성은 validation 후 재시도했습니다.

### StreamArena

88개 admission clip, judge=`gemini-3.8-flash`.

| Arm | Correct |
|---|---:|
| B Qwen3.5-9B sliding window | 7/88 |
| C-local GAMST Context + Qwen3.5-9B | 0/88 |
| C-Gemini GAMST Context + Gemini 3.8 Flash | 3/88 |

Gemini 3.1 Pro는 호출하지 않았습니다. 기존 A 수치와 judge harness가 달라 직접 비교하지 않습니다.

### RepCountA

151개 실제 test 영상의 complete artifact(`capability_lab/results/count_test_all.jsonl`):

| Pipeline | n | MAE | OBO (±1) |
|---|---:|---:|---:|
| Pose native | 151 | 4.404 | 0.437 |
| Pose 1Hz | 151 | 10.868 | 0.172 |
| Pixel native | 151 | 6.556 | 0.397 |
| Pixel 1Hz | 151 | 10.821 | 0.146 |

### MCD-rPPG

40개 실제 영상:

- MediaPipe face + POS: MAE 19.09 bpm, ±5 bpm 45.0%, ±10 bpm 57.5%
- 1Hz: MAE 86.06 bpm, ±5 bpm 0%
- before/after 방향 일치 14/20

## 실제 가중치·병렬 실행

성공: RF-DETR Large, YOLOE-26x, MediaPipe pose/hand/face, CED-Base, TEN-VAD, Nemotron diarization, Qwen3-ASR.

제한/실패:

- SAM 3.1: 공식 16-object checkpoint 구조로 로드되지만 tracker에서 `vision_feat=[5184,0,256]` 오류 반복.
- VDA-L: full concurrent smoke drop 84.8%; solo 53.5%.
- FactorizePhys: checkpoint 로드 성공, 실제 clip에서 Haar face window 부족으로 pulse 미확정.
- ASR: solo 성공, full shared GPU에서 KV cache 부족.
- semantic VLM: full concurrent smoke에서 p95 12.2초까지 증가.

Full smoke: 60.08초 실제 영상, wall RTF 1.0438. 상세 `PARALLEL_SMOKE.md`, solo 상세 `VERIFY.md`.

## Watch / jev / demo

- Watch CRUD, version hash, owner-only update, jev proposal, cooldown, rate limit, evidence contribution, time-window context 구현.
- jev Qwen3.8-27B-FP8 tool call 확인.
- hands-on demo: 실제 `risk` observation을 넣어 Watch alarm 1건과 contribution=1.0 확인.

## 비용·자원 종료

- 온디맨드 RTX/H100은 거절됐고, 승인된 Spot RTX PRO 6000을 사용했습니다.
- SAM/ASR/FactorizePhys 상용 대체 API는 비용 승인 없이 사용하지 않았습니다.
- VM `gamst-par`: **TERMINATED**.

## 인수인계와 PR

- 원문 계획: `PLAN.md`는 수정하지 않았습니다.
- 진행 기록: `RESUME.md`, `HANDOFF.md`.
- GAMST draft PR #352: Watch, provider 변경, 실패 조건과 결과 기록.
- GamstCrew draft PR #23: parallel runtime 구현과 shared-ring/monitor 결과.
- Gamst-bench draft PR #17: 실험 runner, weight manifest, MOT17/StreamArena/RepCount/MCD 결과.
- 세 PR은 실패 모델과 미완성 점을 포함한 상태로 ready/merge 검토가 필요합니다.

## 제한

- 사용자 직접 촬영이 필요한 점프와 사람+소리 확률 구름은 데이터가 없어 실행하지 않았습니다.
- SAM 3.1은 실제 가중치 검증 실패입니다. 상용 대체는 사용자 비용 승인 전 사용하지 않았습니다.
- A(Gemini 3.1 Pro)는 재호출하지 않았습니다.
