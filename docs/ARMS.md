# GAMST benchmark arms

The benchmark profiles are explicit and initially unmeasured. A profile descriptor is not a result.

| Arm | Policy | Perception | Semantic model | Status |
|---|---|---|---|---|
| B | thin | mac-lightweight | consumer LLM | unmeasured |
| C | hybrid | mac-lightweight | selective VLM + consumer LLM | unmeasured |
| D | periodic | mac-lightweight | periodic VLM + consumer LLM | unmeasured |
| E | streaming | streaming-vlm | small streaming VLM + consumer LLM | unmeasured |

Results may be published only after a frozen manifest, real model servers, target hardware, input timing, evidence policy and resource instrumentation are recorded. Unknown metrics remain null.

## 2026-11-16 local execution smoke

B/C/D/E completed one four-frame unscored smoke through real local llama.cpp
b12318 serving pinned Qwen3-VL-2B-Instruct Q8_0 on Apple Silicon. D exercised
periodic VLM calls and E exercised the streaming endpoint. All four traces had
a cited answer and no adapter diagnostics. This establishes executable model
paths only: it is not a held-out quality comparison, resource/cost audit or
default-selection result.
