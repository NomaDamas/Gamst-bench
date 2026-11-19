# GAMST High-Frequency Dataset Acquisition

**Branch:** `feat/gamst-hf-benchmark`

## Decision

The first GAMST-specific benchmark does **not** depend on downloading an
unlicensed internet dataset. It starts with a reproducible synthetic track and
then adds a separately licensed real-video track. This is required because the
benchmark must prove that 1 FPS, a first/last frame pair, and a shuffled stream
cannot solve the task.

## Track A — deterministic synthetic episodes

This track can be generated locally or on GCP without credentials. Every episode
is rendered at 30 or 60 FPS with a fixed seed and includes synchronized lanes:

- RGB video with objects, occlusion, short events and state transitions;
- PCM audio with controlled onset/offset and AV delay;
- physical JSONL (position, velocity, acceleration, contact/rotation);
- immutable truth JSONL (events, relations, states, answer cutoff/deadline).

The generator must produce paired variants from the same seed:

- full stream;
- 4 FPS;
- 1 FPS;
- first/last frames;
- shuffled frames;
- video-only/audio-only/physical-only;
- controlled frame/audio drops and late packets.

The truth file is never supplied to an adapter. It is used only by the scorer.
The first fixture is the existing GamstCapture coin-spin generator; it becomes
one physical-dynamics family, not the whole benchmark.

## Track B — consented real episodes

Use short recordings made by the project owner or explicitly consenting
participants. The capture tool records video, PCM audio and optional IMU into
separate files, with a monotonic capture clock and a manifest. Annotation is
performed after capture using a blinded review form; the annotator does not see
model outputs. Raw media remains private; public artifacts contain hashes,
approved IDs and derived annotations only.

The collection protocol covers:

1. a short event that disappears before the end frame;
2. a multi-step action with a required order;
3. an AV offset or audio-only distinction;
4. occlusion followed by last-seen retrieval;
5. an initial label corrected by later evidence;
6. a physical action (rotation/contact/impact/fall);
7. a deliberate packet gap and recovery.

No participant-identifying or sensitive recordings enter the public repository
without a separate release decision.

## Track C — public external data (optional)

Public sources are candidates, not automatically downloadable assets. Before
use, record the source license, access terms, frame rate, audio availability,
redistribution rule and a dataset hash. Suitable candidates include long-form
streaming-video sets such as Inf-Streams-Eval/Train and licensed egocentric or
sports sources, but their terms and manifests must be reviewed per release.
A paper or GitHub URL alone is not permission to mirror media. If redistribution
is not allowed, run privately and publish only authorized hashes/annotations.

The existing external benchmarks remain comparison tracks; they do not become
GAMST-specific data merely by adding an adapter.

## Canonical episode schema

```json
{
  "episode_id": "hf-000001",
  "source": {"kind": "synthetic|consented|public", "license": "...", "revision": "..."},
  "streams": {
    "video": {"path": "...", "fps": 60, "sha256": "..."},
    "audio": {"path": "...", "sample_rate": 16000, "sha256": "..."},
    "physical": {"path": "...", "sha256": "..."}
  },
  "events": [{"id":"e1", "kind":"impact", "start_ms":1200, "end_ms":1280,
               "modalities":["video","audio","physical"], "evidence_required_ms":500}],
  "states": [{"start_ms":0, "end_ms":1000, "state":{"phase":"preparing"}}],
  "relations": [{"source":"e1", "relation":"causes", "target":"e2"}],
  "queries": [{"at_ms":1500, "deadline_ms":300, "kind":"episode_order",
                "question":"What happened immediately before the impact?",
                "answer":{"event_id":"e0"}}],
  "anti_shortcut": {"min_source_fps":30, "one_fps_score_ceiling":0.35,
                     "requires_order":true, "requires_cutoff":true}
}
```

## Admission gates

An episode is admitted only when all gates pass:

- 1 FPS and first/last controls are below the preregistered ceiling;
- frame shuffle breaks the required answer;
- the answer uses at least two temporal observations;
- future frames after `at_ms` cannot reveal the answer;
- at least one modality ablation fails where multimodal evidence is declared;
- a human review confirms the answer is not visible in a single still image;
- all media/annotation hashes and license metadata are frozen.

If an episode fails a gate, it is a diagnostic fixture and cannot enter the
acceptance split.

## Dataset acquisition automation

The acquisition tool will have separate commands:

```text
prepare-synthetic --seed ... --out ...
validate-episode --episode ...
make-controls --episode ...
annotate-template --episode ...
freeze-manifest --root ... --out manifest.json
```

It will never download public media implicitly. Public acquisition requires an
explicit source manifest and an operator-approved credential/path. A generated
benchmark score is blocked until the manifest, license record, controls and
held-out split are frozen.
