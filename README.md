# GAMST Bench

**Small models. Bigger context.** 저비용 멀티모달 컨텍스트 생성을 위한 인터랙티브 벤치마크 대시보드 템플릿.

- Website: https://gamst-bench.jinminseong.com
- Repository: https://github.com/NomaDamas/Gamst-bench
- Reference: [LiveBench](https://livebench.ai/)의 카테고리별 리더보드와 비용 비교 구성에서 영감을 받았습니다. 별개의 프로젝트이며 LiveBench 데이터나 평가 결과를 사용하지 않습니다.

> **현재 모든 모델 이름과 수치는 가상의 예시입니다. 실제 평가를 실행한 결과가 아닙니다.** 이 저장소는 결과 탐색·공유 템플릿이며 모델 추론 또는 채점 실행기는 포함하지 않습니다.

## Dashboard

- 산점도 점, 성능 막대, 모델 체크박스 선택 → 다른 차트·평균 지표·리더보드 동시 필터링.
- 차원 카드 / 카테고리 선택 → 모든 차트와 순위표의 활성 품질 점수 변경.
- 모델 검색, 모델 계열, 7B 이하 필터, 다중 모델 비교, 필터 초기화.
- 비용 ↔ 지연시간 산점도 축 전환, 표 정렬, 필터 URL 공유, 현재 결과 CSV 다운로드.
- 모바일 레이아웃, 키보드로 조작 가능한 그래프, 스크린리더 레이블, 감소된 모션 설정 지원.

## Benchmark results

<!-- RESULTS:START -->

> **SYNTHETIC DEMO — 실제 벤치마크 결과 아님. 모델과 수치는 모두 가상입니다.**

Release: **2026-11-14** · 8 models · 6 dimensions

| Rank | Model | Family | Params (B) | Overall | Visual | OCR | Temporal | Audio | Context | Factuality | Cost / 1k clips (USD) | p50 latency (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Reference 32B | Reference | 32 | 91.3 | 92.1 | 91.3 | 89.8 | 87.4 | 94.6 | 92.5 | 1.82 | 3.42 |
| 2 | GAMST 7B | GAMST | 7 | 88.9 | 90.4 | 88.2 | 87.6 | 84.1 | 93.2 | 90.1 | 0.48 | 1.24 |
| 3 | Reference 14B | Reference | 14 | 86.4 | 88.2 | 86.4 | 84.5 | 81.6 | 90.1 | 87.8 | 1.06 | 2.28 |
| 4 | GAMST 3B | GAMST | 3 | 84.1 | 86.2 | 83.4 | 81.8 | 78.2 | 89.4 | 85.8 | 0.24 | 0.82 |
| 5 | Context Base 7B | Baseline | 7 | 81.7 | 84.8 | 79.6 | 80.1 | 76.3 | 86.7 | 82.5 | 0.64 | 1.86 |
| 6 | Fusion Mini 4B | Baseline | 4 | 79.6 | 80.3 | 78.1 | 76.8 | 82.4 | 81.2 | 78.6 | 0.36 | 0.95 |
| 7 | Vision Lite 3B | Baseline | 3 | 76.4 | 82.1 | 85.2 | 71.3 | 62.4 | 76.8 | 80.6 | 0.31 | 1.12 |
| 8 | GAMST 1B | GAMST | 1 | 73.0 | 76.5 | 73.8 | 68.9 | 65.2 | 79.6 | 74.2 | 0.09 | 0.38 |

Generated from [data/benchmark.json](data/benchmark.json) using `npm run results`.

<!-- RESULTS:END -->

## Scoring and units

- **Overall** = (Visual + OCR + Temporal + Audio + Context + Factuality) / 6. 내부 계산은 반올림하지 않으며 화면과 README에 소수점 한 자리로 표시합니다.
- 모든 품질 점수는 0–100이며 높을수록 좋습니다. 개별 차원의 채점 프로토콜은 실제 평가 시 정의해야 합니다.
- **Cost**: 클립 1,000개당 추론 비용(USD). 입력·출력 토큰 또는 GPU 시간, 하드웨어 비용 산식, 클립 길이를 실제 실행에 맞게 기록해야 합니다.
- **Latency**: 모델별 p50(초). 대시보드 평균은 선택된 모델의 p50 값의 산술평균이며, 전체 요청을 합친 p50이 아닙니다.
- **Small model**: 파라미터 수 ≤ 7B.
- 모든 필터는 AND로 결합됩니다. 모델 다중 선택 내부는 OR입니다. 검색/계열 변경으로 선택 모델이 숨겨진 경우 칩을 제거하거나 Reset으로 복구할 수 있습니다.
- 카테고리 점수는 현재 선택 모델들의 평균입니다. 품질 산점도와 순위표는 활성 카테고리 점수를 사용합니다. 축 범위는 선택에 따라 움직이지 않습니다.

## Run locally

Node.js 22.22+ 권장.

```bash
npm ci
npm run dev
```

```bash
npm test
npm run results:check
npm run build
npm run preview
```

## Add actual results

1. `data/benchmark.json`의 모델과 차원 데이터를 교체합니다. `id`는 고유하게 유지하고, 각 모델은 모든 차원의 점수를 가져야 합니다. `parameters`는 B 단위, `cost`는 USD/1,000 clips, `latency`는 초입니다.
2. `release`와 `version`을 갱신합니다. 실제 측정 데이터만 포함됐을 때 `isDemo`를 `false`로 바꿉니다. 아래의 연구 프로토콜과 실행 증빙을 채우고 웹사이트의 샘플 안내 문구도 실제 데이터에 맞게 변경합니다.
3. `npm run results`로 README 표를 다시 생성합니다. 웹사이트는 같은 JSON을 직접 읽으므로 데이터가 이중 관리되지 않습니다.
4. `npm test && npm run results:check && npm run build`를 실행하고 변경 사항을 커밋합니다.

### Required evidence for a real release

현재는 모두 미정이며 예시 수치에서 추론할 수 없습니다.

- 데이터셋 이름·버전·라이선스, 샘플 수, split, 클립 길이와 모달리티 구성
- 모델 체크포인트·revision, 양자화, 컨텍스트 길이, 프롬프트, 생성 설정 및 seed
- 하드웨어·런타임·배치 크기, warm-up, 반복 횟수, 실패/재시도 처리
- 차원별 정답·채점 규칙, 평가 모델을 쓰는 경우 모델 버전과 프롬프트
- 비용 산식 및 가격 기준일, 측정 로그와 원시 결과, 신뢰구간 산출 방법

## Deploy

Cloudflare Workers Static Assets에 정적 파일을 배포합니다. `wrangler.jsonc`의 Custom Domain은 **gamst-bench.jinminseong.com**입니다. 메인 블로그 `jinminseong.com`을 수정하지 않습니다.

```bash
npx wrangler login
npm run deploy
```

Cloudflare 계정에 해당 DNS zone과 Worker 배포 권한이 필요합니다. Custom Domain 배포 시 Cloudflare가 서브도메인 DNS·인증서를 관리합니다. 자격 증명은 저장소에 넣지 않습니다.

`.github/workflows/ci.yml`은 push/PR에서 테스트·README 동기화·빌드를 확인합니다. 수동 배포는 위 명령으로 실행합니다. 자동 배포를 원하면 Cloudflare Workers Builds에서 이 저장소의 `main`을 연결하고 build `npm run build`, deploy `npx wrangler deploy`를 설정하세요.

## Stack

React · TypeScript · Vite · native SVG charts · Vitest / Testing Library · Cloudflare Workers Static Assets. 외부 차트 서비스나 API 키 없이 탐색 기능이 동작합니다.
