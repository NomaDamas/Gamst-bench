# GAMST Bench

**Less compute. Keep what matters.**

기존 에이전트에 중요한 정보를 적은 자원으로 제때 전달하는지 평가하는 **컨텍스트 파이프라인 벤치마크**.

**[대시보드](https://gamst-bench.jinminseong.com)** · [평가 프로토콜](docs/PROTOCOL.md) · [실행 가이드](docs/RUNBOOK.md) · [주석 규칙](docs/ANNOTATION.md) · [어댑터 계약](docs/ADAPTERS.md)

> 공개 데이터는 36개 합성 시나리오 × A/B/C/D, 총 144개 프로토콜 검증 결과입니다. 실제 모델 추론·물리 센서 실험·8시간 soak를 실행한 결과가 아닙니다. 샘플 성능으로 품질 보존이나 비용 절감을 주장하지 않습니다.

## What is evaluated

- **A:** VLM 중심 처리. **B:** 경량 인식만. **C:** 선택적 호출을 포함한 Gamst 혼합. **D:** 동일 모델의 주기적 혼합.
- 평가 단위: 센서 + 인식 모델 + VLM + 정책 + 메모리 + 소비자 LLM + 하드웨어.
- 핵심 지표: **기한 내 근거 있는 성공률**. 정답, 의미적으로 유효한 근거, 시간 조건을 모두 충족해야 성공합니다.
- 6개 suite: 짧은 사건 / 작은 의미 변화 / 객체·상태 메모리 / 음성·영상 수정 / 질문 이전 문맥 보존 / 단절·과부하 복구.
- 전체 파이프라인 비용, p95 답변 지연, 중요 사실 재현율, 근거 없는 주장, 오래된 상태 오류, 기권, 시간당 오탐, 메모리와 드롭을 함께 공개합니다.
- 기존 FastBench 등의 공식 프로토콜 점수는 별도 결과이며 Gamst 종합 점수에 섞지 않습니다.

## Benchmark results

<!-- RESULTS:START -->

> **SYNTHETIC — 합성 프로토콜 검증. 실제 모델 성능·절감 효과를 증명하지 않습니다.**

Release 2026-11-14 · gamst-context-v0.2 · 144 configuration-task runs

| Configuration | Policy | Runs | Grounded & on time | Critical recall | Answer p95 (ms) | Full pipeline USD/h | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A · VLM-centered | vlm | 36 | 0.0% | 83.3% | 3100 | 3.12 | synthetic |
| B · Thin models only | thin | 36 | 66.7% | 66.7% | 780 | 0.24 | synthetic |
| C · GAMST hybrid | hybrid | 36 | 97.2% | 97.2% | 1250 | 0.96 | synthetic |
| D · Periodic hybrid | periodic | 36 | 88.9% | 88.9% | 1950 | 1.68 | synthetic |

- **C vs A: not_passed** — cost ratio 0.31, p95 ratio 0.40, quality difference 0.14; 36 session clusters.
- **C vs D: not_passed** — cost ratio 0.57, p95 ratio 0.64, quality difference 0.08; 36 session clusters.

Official FastBench / SPOT-Bench / Inf-Streams-Eval: **not measured**.

Frozen plan SHA256: `07b58ddb85ad77dd2b7cc2260a2f96023b1dd50b2b59306ed513cb4bf4852a1a`

Source manifest: [data/release.json](data/release.json). Generated with `npm run results`.

<!-- RESULTS:END -->

## Local development

Node.js 22.22+와 Python 3.10+를 사용합니다. 평가 코어는 Python 표준 라이브러리만 사용하며 모델을 자동 설치하지 않습니다.

```bash
npm ci
npm run dev
npm test
npm run test:python
npm run results:check
npm run build
```

대시보드는 구성/과제/정책/센서/하드웨어/증거 수준/비용 예산/사건 길이로 교차 필터링합니다. URL 공유, CSV 내보내기, 증거 타임라인, 자원 시계열과 세션 단위 95% 신뢰구간을 제공합니다. 화면의 탐색용 응답 기한은 사전 고정한 수용 기준을 바꾸지 않습니다.

## Reproduce the evaluation pipeline

```bash
# 출력 폴더는 존재하지 않는 새 경로를 지정합니다.
python3 -m gamst_bench demo --out runs/demo-001
python3 -m gamst_bench validate --plan runs/demo-001/plan.json
python3 -m gamst_bench evaluate \
  --plan runs/demo-001/plan.json \
  --traces runs/demo-001/traces.json \
  --assessments runs/demo-001/assessments.json \
  --out runs/demo-001/recomputed.json
```

`demo`는 합성 프로토콜만 검증합니다. 실제 평가에서는 freeze → collect → 외부 채점 → evaluate 순서로 실행하세요. 계획과 입력 해시, 채점-실행 연결, 누락된 쌍, 실패 페널티, 세션 단위 bootstrap을 검사합니다. 합성 자료는 수용 판정을 통과할 수 없습니다.

실제 모델 어댑터, 외부 벤치마크 결과 import, 장시간 수집 명령은 [RUNBOOK](docs/RUNBOOK.md)에 있습니다. 참조 어댑터의 실제 체크포인트 호환성은 미검증이며, 기존 Gamst 설치와 명시적으로 선택한 모델·플러그인이 필요합니다.

## Publish new evidence

1. 실험 계획·입력·코드·모델 revision을 고정하고 계획 해시를 실행 전 별도 기록합니다.
2. 동일 입력과 소비자 LLM을 유지하여 A/B/C/D를 수집합니다. 실패·타임아웃을 삭제하지 않습니다.
3. `assess-template`으로 채점 양식을 만들고 원시 증거를 확인해 사람이 채웁니다. 값의 해시 일치는 정확성이나 독립성을 보증하지 않습니다.
4. `data/release.json`에서 검토된 plan/traces/assessments를 지정합니다. `npm run results`가 공개 JSON과 README를 같은 소스에서 다시 계산합니다.
5. 테스트·빌드를 통과한 뒤 `npm run deploy`로 Cloudflare에 배포합니다.

관측 원본에 개인정보가 있다면 공개 저장소에 올리지 않습니다. 공개용 식별자와 허가된 자료만 사용하고 비공개 원본의 해시·평가 절차를 기록합니다. 기본 `.gitignore`는 `runs/`를 제외합니다.

## Acceptance and limitations

엔지니어링 게이트는 비용 비율 ≤0.8, p95 지연 비율 ≤0.9, 평균 품질 차이 ≥0, 선언된 중요 사실 보존입니다. 점추정치와 세션-paired bootstrap 95% 구간 모두 기준을 충족해야 합니다. held-out, 실측, 최소 독립 세션 수도 필요합니다. 현재 공개 결과는 **not passed**입니다.

- `measured` 표기나 `numeric_pass_requires_audit`는 실제 모델 실행·측정·채점의 진위를 인증하지 않습니다.
- 기본 수집기의 RSS는 어댑터 프로세스 트리만 측정합니다. 별도 모델 서버·GPU 메모리·에너지·하드웨어 비용은 추가 계측이 필요합니다.
- 근거·정답의 의미 판단은 외부 검수입니다. 모델의 자기보고 confidence를 정답으로 쓰지 않습니다.
- 타임아웃에는 사전 정의한 지연 페널티를 적용합니다. 잘못된 빠른 답은 품질 0이며, 비용·지연만으로 통과하지 않습니다.
- 웹 UI 자동화 도구가 연결되지 않은 환경에서는 DOM 기반 상호작용 테스트와 빌드/HTTP 검증을 수행합니다. 실제 브라우저 시각 검증은 별도입니다.

## Deployment

Cloudflare Workers Static Assets · **gamst-bench.jinminseong.com**. 기존 `jinminseong.com` 블로그와 분리된 Worker입니다.

```bash
npm run deploy
```

GitHub Actions는 Python 평가 테스트, 웹 상호작용 테스트, 소스 결과 동기화와 빌드를 검증합니다. 자동 배포는 설정하지 않았으며 `npm run deploy`로 배포합니다.

## Research foundation

[Gamst](https://github.com/NomaDamas/Gamst)의 [확장 계획](https://github.com/NomaDamas/Gamst/blob/HEAD/docs/perception-expansion-plan.md), [평가 계약](https://github.com/NomaDamas/Gamst/blob/HEAD/docs/perception-evaluation.md), [실시간 계약](https://github.com/NomaDamas/Gamst/blob/HEAD/docs/realtime.md)을 토대로 설계했습니다. 외부 기준은 [FastBench](https://github.com/Ashone3/FastBench), [SPOT-Bench](https://dibschat.github.io/SPOT-Bench/), [Inf-Streams-Eval](https://research.nvidia.com/labs/eai/publication/streamingvlm/). 대시보드 디자인은 [LiveBench](https://livebench.ai/)에서 영감을 받았습니다. 각 프로젝트와 별개이며 공식 제휴나 재현 성공을 주장하지 않습니다.
