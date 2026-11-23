# GAMST setup roles and defaults (evidence map)

GAMST perception is organised into roles (`vision.detect`, `vision.rotation`,
`audio.asr`, `vision.semantic_scene`, ...). Several models can fill a role.
GamstCrew's agentic setup (`gamst setup` / MCP `plan_setup` + `apply_setup`)
detects the host, picks a hardware-tier default for every role the goal needs,
installs only those models with sha256-verified weights, and writes
`~/.config/gamst/profile.json`; GAMST's `ProfileRuntime` runs the profile as
ordinary plugins. The authoritative role table, tiers and profile schema live in
GamstCrew `docs/agentic-setup.md`; this page records where the numbers behind
the defaults come from.

| Tier | Detection | Semantic scene | ASR |
|---|---|---|---|
| cpu-only | RF-DETR Nano | SmolVLM2 500M | Faster-Whisper Small |
| apple-mps | RF-DETR Nano (MPS) | SmolVLM2 500M (CPU) | Faster-Whisper Small |
| cuda < 24 GB | RF-DETR Nano | SmolVLM2 500M | Faster-Whisper Small |
| cuda >= 24 GB | RF-DETR Large | Qwen3.5-9B | Qwen3-ASR 1.7B |

YOLOE-26s/26x is an optional open-vocabulary detector; `vision.rotation` needs
no learned model and uses whatever detector, ROI or motion region is available.

## Evidence behind the numbers

| Source | What it measured | Used for |
|---|---|---|
| `experiments/parallel-gamst-2026-11-20/VERIFY.md` (RTX PRO 6000 96 GB) | Solo real-video latency/memory per model, e.g. RF-DETR Large 7.9 ms compute / 9.9 ms p95 / 910 MiB, YOLOE-26x 12.0 ms / 16.9 ms p95 / 1710 MiB, MediaPipe pose heavy 32.3 ms, hand 9.8 ms | CUDA tier memory reservations and verification status |
| `experiments/parallel-gamst-2026-11-20/WEIGHTS.md` | Pinned weight URLs and sha256 | `apply` download verification |
| Gamst PR #357 (Apple Silicon, real clips) | YOLOE-26s p50 45.7 ms on MPS vs 157.1 ms on CPU; rotation observed 343/375 frames on a real table-spin clip | Apple-MPS device choice for YOLOE; rotation status |
| GamstCrew PR #24 | Real `apply` of MediaPipe Pose Lite with sha256 verification and idempotent re-run | Installer behaviour |

Everything else in the registry is an estimate and is labelled as such. No
default is claimed to be quality-optimal: the matched held-out comparison that
would select defaults from measurements has not been run. Rotation count
accuracy on real 240 fps hand tosses is not yet measured; 30/60 fps cameras are
reported as `undersampled` for tossed coins (36-40 rev/s).

The benchmark/billing harness formerly kept in the Gamst repository is archived
in [gamst-repo-benchmarks.md](archive/gamst-repo-benchmarks.md).
