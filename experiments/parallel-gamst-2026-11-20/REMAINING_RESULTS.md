# 남은 벤치마크 진행 기록

## MCD-rPPG

실제 MCD-rPPG 40개 영상(20 subjects × before/after)을 실행했습니다.

| pipeline | videos | MAE | ±5 bpm | ±10 bpm | 기타 |
|---|---:|---:|---:|---:|---|
| MediaPipe face + POS | 40 | 19.09 bpm | 0.45 | 0.575 | before/after 방향 일치 14/20 |
| 동일 pipeline 1Hz | 40 | 86.06 bpm | 0 | 0 | Nyquist 한계 |

이 결과는 기존 capability-lab light rPPG 결과와 일관된 실패 양상입니다. FactorizePhys parallel adapter는 별도 실행에서 얼굴 window 부족으로 pulse output을 확정하지 못했습니다.

## RepCount

실제 RepCountA test Lance split에서 pose pipeline으로 전체 151개를 실행 중입니다. 완료 전 중단하지 않습니다.

중간 44개 표본:
- pose native: MAE 3.205, OBO 0.386
- pose 1Hz: MAE 11.0, OBO 0.182

중간값은 전체 결과가 아니며 최종 결과로 사용하지 않습니다.

## StreamArena

admission 88개에 대해 실제 clip 기반 arm을 생성하고, `gemini-3.8-flash`로 동일 judge protocol을 실행했습니다.

| arm | 응답/평가 | correct | rate |
|---|---:|---:|---:|
| B Qwen3.5-9B sliding-window | 88 | 7 | 0.080 |
| C-local | 88 | 0 | 0.000 |
| C-Gemini | 88 | 3 | 0.034 |

- 초기 B 오류 행은 id별 최신 성공 행으로 정리했습니다.
- C arms는 GAMST Context를 사용했습니다. C-local/C-Gemini 모두 동일한 context generation path입니다.
- judge는 `gemini-3.8-flash`입니다. Gemini 3.1 Pro는 재호출하지 않았습니다.
- 이 수치는 기존 A 결과와 judge harness가 다르므로 직접적인 승패 비교가 아닙니다. A 재실행은 하지 않았습니다.
