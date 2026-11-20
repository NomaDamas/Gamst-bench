# MOT17 B / C-local / C-Gemini 결과

- 실제 데이터: MOT17-09-FRCNN, MOT17-04-FRCNN
- RF-DETR Large 실제 가중치 출력으로 GAMST RiskField를 재생성했습니다.
- jev(Qwen3.8-27B-FP8)가 사용자 문장을 `create_watch` 인수로 변환했습니다.
- 첫 실행은 jev가 잘못된 `subject_id`를 만들어 Watch가 평가되지 않았습니다. jev 재시도 검증에서 `subject_id=local-user`를 강제하고 다시 실행했습니다. 아래 표는 재실행 결과입니다.
- B는 Qwen3.5-9B 슬라이딩 프레임, C-local은 같은 Watch alarm + Qwen3.5-9B, C-Gemini는 같은 Watch alarm + `gemini-3.8-flash`입니다.

| Seq | Arm | Frame precision | Frame recall | Visits alerted / 3 | False alerts | Alert latency (s) |
|---|---|---:|---:|---:|---:|---|
| MOT17-09 | GAMST RiskField | 0.649 | 0.963 | 3 | 0 | +0.40, -0.30, 0.00 |
| MOT17-09 | B | 0.703 | 0.712 | 2 | 0 | +1.00, -0.07 |
| MOT17-09 | C-local | 0.687 | 0.721 | 1 | 0 | +3.40 |
| MOT17-09 | C-Gemini | 0.649 | 0.963 | 2 | 0 | -0.30, 0.00 |
| MOT17-04 | GAMST RiskField | 0.742 | 0.972 | 2 | 1 | +0.60, -0.33 |
| MOT17-04 | B | 0.782 | 0.936 | 2 | 1 | +1.00, +0.07 |
| MOT17-04 | C-local | 0.742 | 0.972 | 1 | 0 | +0.60 |
| MOT17-04 | C-Gemini | 0.742 | 0.972 | 2 | 1 | +6.60, -0.33 |

## 해석

- 이 두 시퀀스에서는 C-Gemini가 GAMST RiskField의 프레임 점수와 같았습니다. 이는 전체 모델 일반 우열이 아니라 이 두 시퀀스·이 Watch 규칙의 결과입니다.
- C-local은 C-Gemini보다 알림을 덜 내보냈습니다. C-local은 정답을 임의로 보충하지 않고 alarm context만 사용합니다.
- `-` latency는 ground-truth visit 시작 전에 알림이 발생했다는 뜻입니다. 따라서 조기 알림을 정확한 알림으로 단순 해석하면 안 됩니다.
- 기존 capability-lab의 light detector 결과와 직접 비교하지 않습니다. 이번 결과는 RF-DETR Large와 실제 병렬 실험 stack의 결과입니다.

원시 산출물: VM `/srv/par/eval/mot17/<sequence>/arms.json`.
