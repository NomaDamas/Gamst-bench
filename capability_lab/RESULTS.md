# GAMST capability checks on small real data (2026-11-20)

These checks follow `docs/capabilities.md` in the GAMST repo. Each check runs a light model, with no task training, at the source rate. The same model is also run on 1 Hz samples, which is what a 1 FPS VLM observer sees. All data is real, public and labelled by humans or sensors. No synthetic data is used. Raw outputs are in `capability_lab/results/`.

## Summary

| Capability | Data (ground truth) | Native rate | 1 FPS observer | Verdict |
|---|---|---|---|---|
| ② Moment capture + physics: jump height, camera | TU Wien JumpMetric, 145 well-executed jumps, Kinect 30 Hz (`height_measured`) | **MAE 31 mm, 79 % within ±50 mm** | MAE 131 mm, 21 % within ±50 mm | Works |
| ② Jump height, accelerometer only | same, neck/chest/hip IMU 100 Hz | MAE 87 mm, 32 % within ±50 mm | – | Not yet; simple free-fall detection is not enough |
| Count: repetitions | RepCountA test, 151 videos (human counts) | pose: **MAE 0.429, OBO 0.437** | MAE 0.736, OBO 0.172 | Works roughly. 1 FPS loses more than half the OBO hits. Gemini 3.1 Pro at 8 FPS is more accurate (124-video subset: OBO 0.605 vs 0.379), at about 17k tokens per video. |
| ③ Rhythm: heart rate from a phone camera | MCD-rPPG, 40 phone videos (synchronous contact PPG) | **50 % within ±5 bpm**, MAE 19.8 bpm | 0 % (Nyquist 0.5 Hz < pulse) | Half; fails mostly on high heart rates |
| ① Probability cloud, daytime | MOT17-09, shop entrance zone (human boxes) | frame recall 0.86, precision 0.73 | recall 0.87, precision 0.75 | Mechanics work. High frequency adds nothing here, because people walk slowly. |
| ① Probability cloud, night | MOT17-04, road zone | frame recall 0.21, precision 0.89 | recall 0.14 | Fails; the light detector misses small people at night |
| Memory from the state chain | the two MOT17 zone runs | visits 2 vs truth 3 (09); 1 vs 3 (04) | – | The chain answers correctly from what it stored, but detector misses become memory misses |

## Details

### ② Jump height (`jump_physics.py`)

- **Data:** TU Wien JumpMetric (`doi:10.48436/c0584-yqb91`, CC-BY-4.0). 44 subjects × 5 countermovement jumps. 191 jumps have a valid ground truth; 145 of those are marked well-executed.
- **Moment capture:**
  - Takeoff is the last frame before both foot joints rise more than 20 mm.
  - Height = pelvis height at takeoff − pelvis height at the apex.
  - The second estimator uses flight time while the feet are up: h = g·T²/8.
- **Bias correction:** every estimator has a constant setup bias of about −120 mm against `height_measured`. It is removed with a leave-one-subject-out offset: the median error of the other 43 subjects. The test subject is never used to calibrate itself.
- **Results (well-executed jumps, after offset correction):**

  | Estimator | MAE | SD | Within ±30 mm | Within ±50 mm |
  |---|---:|---:|---:|---:|
  | Takeoff rise | 31.1 mm | 40.8 mm | 60.7 % | 79.3 % |
  | Flight time | 32.7 mm | 42.5 mm | 53.1 % | 79.3 % |
  | IMU free fall | 86.9 mm | 103.0 mm | 21.4 % | 32.4 % |
  | 1 Hz pelvis rise | 130.9 mm | 153.0 mm | 12.4 % | 20.7 % |

- **Reference:** the dataset paper reports its best camera result as −15.8 ± 23.3 mm (pelvis). This simple estimator is not at that level yet.
- **Same data through the GAMST provider** (`jump_provider.py` → `gamst/providers/flight.py`). The provider adds two-sample contact debouncing and a ballistic parabola fit of the airborne foot clearance, used on 98.6 % of jumps. Well-executed jumps, after the leave-one-subject-out offset:

  | Estimator | MAE | Within ±50 mm |
  |---|---:|---:|
  | Rise | 34.4 mm | 78.6 % |
  | Flight | 35.7 mm | 80.7 % |

  The same provider on 1 Hz samples detects **0 of 145** jumps. The median fitted gravity is 8.6 m/s², because Kinect foot joints are not perfectly ballistic.

### Count (`count_repcount.py`)

- **Data:** RepCountA test split (`lmms-lab-eval/repcounta-lance@ae2e0b0`). 151 videos with a count.
- **Counter:**
  - Input: MediaPipe Pose Lite landmarks at the video rate.
  - Signal: the PCA component with the purest spectral peak in the 0.15–3 Hz band.
  - Count: peaks spaced at least 0.6 × the dominant period apart.
- **Results (all 151 videos):**

  | Input | MAE (normalised) | OBO |
  |---|---:|---:|
  | Pose, native rate | 0.429 | 0.437 |
  | Pose, 1 Hz | 0.736 | 0.172 |
  | Raw-pixel PCA, native rate | 0.450 | 0.397 |
  | Raw-pixel PCA, 1 Hz | 0.706 | 0.146 |

- **Reference:** TransRAC (CVPR 2022), a trained model, reports MAE 0.443 and OBO 0.291 on RepCount-A test. Those numbers come from the paper, not from this run, so the comparison is indicative only.
- **Gemini 3.1 Pro count reference** (`gemini_count.py`, Vertex, low media resolution): 124 of the 151 videos had finished at the time of writing; the run continues. On those 124 videos only, all rows compare like with like:

  | Arm | Videos | MAE | OBO | Prompt tokens per video (median) |
  |---|---:|---:|---:|---:|
  | Gemini 3.1 Pro, 8 FPS | 124 | **0.242** | **0.605** | 17,182 |
  | Gemini 3.1 Pro, default 1 FPS | 124 | 0.434 | 0.387 | 2,200 |
  | Light pose counter, native rate | 124 | 0.416 | 0.379 | 0 (local CPU) |
  | Light pose counter, 1 Hz | 124 | 0.689 | 0.177 | 0 |

- **Reading:**
  - A strong VLM given dense frames is the most accurate counter here.
  - The free local light counter is level with Gemini at its default 1 FPS: MAE 0.416 vs 0.434, OBO 0.379 vs 0.387.
  - For count, the GAMST case is cost and always-on operation, not accuracy. The counter needs a stronger repetition model before it can match dense Gemini.

### ③ Heart rate (`rhythm_rppg.py`)

- **Data:** MCD-rPPG (`kyegorov/mcd_rppg@bf59b3c`, CC-BY-4.0). 20 seeded subjects, phone camera, before and after 15 squats. The first 60 s of each video is used.
- **Method:**
  - Face region: MediaPipe BlazeFace box interior.
  - Pulse signal: POS projection, band-passed to 0.7–3 Hz.
  - Heart rate: the Welch spectral peak.
  - Ground truth: the same estimate on the synchronous contact PPG.
- **Results:**
  - Native rate: 50 % within ±5 bpm, MAE 19.8 bpm.
  - Median absolute error: 3.5 bpm after exercise, 10 bpm at rest.
  - The before/after direction matches in 13 of 20 subjects.
  - At 1 Hz, 0 % within ±5 bpm: sampling at 1 Hz cannot represent a 1–2 Hz pulse.

### ① Probability cloud + memory (`zone_risk.py`)

- **Data:** MOTChallenge MOT17-09 and MOT17-04 (CC BY-NC-SA 3.0), with human pedestrian boxes.
- **User rule:**
  - MOT17-09: "someone at the shop entrance".
  - MOT17-04: "someone on the road in front of the car".
  - Each zone was drawn on frame 1, before any result was computed.
- **Model:**
  - Detector: MediaPipe EfficientDet-Lite0 person detector on every frame.
  - Risk score: log-odds evidence (a Gaussian kernel on the distance from a person's feet to the zone) with exponential decay (τ 1.5 s).
  - Alarm: hysteresis, ON at p ≥ 0.8 and OFF at p ≤ 0.4.
  - Memory: alarm events are stored in GAMST's `SemanticStateChain`.
- **Results:**

  | Sequence | Rate | Frame recall | Frame precision | Visits detected |
  |---|---|---:|---:|---:|
  | MOT17-09 | 30 FPS | 0.86 | 0.73 | 2 of 3 |
  | MOT17-09 | 1 FPS | 0.87 | 0.75 | 2 of 3 |
  | MOT17-04 | 30 FPS | 0.21 | 0.89 | 1 of 3 |
  | MOT17-04 | 1 FPS | 0.14 | 1.00 | 1 of 3 |

- **Alarm stability:** a naive p ≥ 0.5 threshold switched the alarm 3 times on MOT17-09 and 4 times on MOT17-04. Hysteresis switched it 4 and 2 times.
- **Memory answers from the chain:**
  - MOT17-09: 2 visits, last starting at 13.3 s (truth: 3 visits, last at 15.8 s).
  - MOT17-04: 1 visit, last at 11.3 s (truth: 3 visits, last at 33.9 s).

## What this says

1. **Physics measurement is the clear win.** At 30 fps, capturing the takeoff moment measures jump height within about 3 cm, while 1 Hz sampling is more than four times worse. This is the most direct "a VLM watching at 1 FPS cannot do this" result.
2. **Count and rhythm depend on frame rate.** Both drop sharply at 1 Hz; heart rate is impossible in principle at that rate. Both need better light models before they are product-grade.
3. **The probability cloud and memory are limited by the detector, not the maths.** These two sequences do not contain fast or audio-coupled events, so they cannot show a high-frequency advantage. The next check needs real footage where people enter and leave quickly, recorded with audio, and a stronger person detector.
