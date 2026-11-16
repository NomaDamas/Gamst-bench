# Running a reproducible experiment

Python 3.10+ is sufficient for the collector/scorer; real perception requires your existing Gamst/model environment. Start from `fixtures/protocol-v3-generated/plan.json` as a **schema example**, not real test data. The fixture generator and its outputs are synthetic.

## 1. Prepare and freeze

Create a new directory such as `runs/experiment-001` and author `draft.json`. Replace fixture tasks with licensed, timestamped real recordings and pre-registered annotations. Pin dataset revision, VLM/consumer revisions, prompt hash, hardware, precision, plugin dependencies, memory window, call policy, sensor track, warm state, rate card and resource allocation. Set `evidence` to `measured` only for actual measured collection. `held_out` can be true only for previously unused test sessions. Preserve an external pre-run timestamp/commit of the frozen hash; file hashes alone do not prove preregistration.

Create `commands.json`, mapping every configuration ID to its argv list:

```json
{
  "A": ["/absolute/path/to/python3", "-m", "gamst_bench.adapters.gamst_http", "--vlm-interval", "1"],
  "B": ["/absolute/path/to/python3", "-m", "gamst_bench.adapters.gamst_http"],
  "C": ["/absolute/path/to/python3", "-m", "gamst_bench.adapters.gamst_http", "--semantic-interval", "5", "--novelty-threshold", "0.08"],
  "D": ["/absolute/path/to/python3", "-m", "gamst_bench.adapters.gamst_http", "--semantic-interval", "5"]
}
```

Replace the executable path and supply actual local endpoints/plugins as described in [ADAPTERS](ADAPTERS.md). Configuration policy comes from the plan, not from the configuration ID. Commands alone do not pin mutable server weights or environment variables; record their resolved versions and hashes in the frozen plan's additional experiment metadata.

Set `execution_sha256` in the draft to the canonical digest of commands. Create and freeze a runtime manifest with `gamst_bench.manifest.freeze_manifest`; include the exact 40-character commits for `gamst`, `gamstcrew`, and `gamst-bench`, set its `manifest_sha256` into the measured plan as `runtime_manifest_sha256`, or pass the manifest to the freeze command:

```python
from gamst_bench.contracts import read, digest, write_new
plan = read('runs/experiment-001/draft.json')
plan['execution_sha256'] = digest(read('runs/experiment-001/commands.json'))
write_new('runs/experiment-001/ready.json', plan)
```

```bash
python3 -m gamst_bench freeze --plan runs/experiment-001/ready.json --manifest runs/experiment-001/runtime-manifest.json --out runs/experiment-001/frozen.json
python3 -m gamst_bench validate --plan runs/experiment-001/frozen.json
```

## 2. Collect and assess

Start your pinned model servers and configure the installed plugins. Use a new output directory; tools refuse to overwrite previous artifacts.

```bash
python3 -m gamst_bench collect --plan runs/experiment-001/frozen.json --commands runs/experiment-001/commands.json --manifest runs/experiment-001/runtime-manifest.json --out runs/experiment-001/collection
python3 -m gamst_bench assess-template --traces runs/experiment-001/collection/traces.json --out runs/experiment-001/assessment-draft.json
```

Fill the generated review form according to [ANNOTATION](ANNOTATION.md), save it as `assessments.json`, and attach accounting artifacts. No model-generated self-grade is accepted automatically. The collector saves each pair immediately, then writes `complete.json` and combined `traces.json`. An interrupted directory without completion is not a complete experiment. Preserve it and rerun into a new directory; do not silently exclude partial failures.

```bash
python3 -m gamst_bench evaluate --plan runs/experiment-001/frozen.json --traces runs/experiment-001/collection/traces.json --assessments runs/experiment-001/assessments.json --manifest runs/experiment-001/runtime-manifest.json --out runs/experiment-001/report.json
```

## 3. Continuous diagnostics

Use an inline-packet plan for the supplied repeat stress harness (blob inputs are rejected). Repeated recordings do not establish long-horizon task quality. Run separately for each configuration and duration:

```bash
python3 -m gamst_bench soak --plan runs/experiment-001/frozen.json --commands runs/experiment-001/commands.json --system C --seconds 1800 --out runs/experiment-001/soak-C-30m
```

Use `7200` and `28800` for 2 h / 8 h. The process remains alive throughout each run. Inspect manifest status, output hash chain, queue/memory trajectory and separate GPU/server instrumentation. The collector intentionally limits output volume; hitting caps is a failed/incomplete diagnostic, not successful stability. Never claim a duration until it actually completes.

## 4. External protocol results

Run official tools separately and create a score JSON with `benchmark`, `protocol_revision`, `dataset_revision`, `scorer_revision`, `system_id`, `metric`, `split`, `evaluation_mode`, numeric `score`/`scale`, `artifact_sha256`, `source_url`, `configuration_sha256` and `protocol_modified:false`. Configuration SHA256 must equal `digest(system)` for the full configuration in the report. The source URL must point to accessible HTTPS evidence, and artifact SHA256 must identify the actual output. Reviewers verify content; the importer only checks the metadata contract.

```bash
python3 -m gamst_bench import-official --report runs/experiment-001/report.json --score runs/experiment-001/fastbench-score.json --out runs/experiment-001/report-with-fastbench.json
```

Measured scores cannot be attached to a synthetic report. For publication, optionally add `"official_scores": ["path/to/fastbench-score.json"]` to `data/release.json`; the publication generator revalidates imports while recomputing the main report. Official scores stay separate and do not alter acceptance gates.

## 5. Publish

Copy only privacy-reviewed, reproducible source artifacts into the repository and update `data/release.json` paths. Then run:

```bash
npm run results
npm run results:check
npm run test:python
npm test
npm run build
npm run deploy
```

README and dashboard JSON derive from the same traces/assessments. A UI filter or exploratory deadline never changes frozen acceptance. GitHub CI checks source synchronization, Python behavior, React interactions and the build; deployment is an explicit release command. Real-model quality, independent review and long-duration stability cannot be replaced by passing software tests.

## GCP native FastBench entry point

Use `python3 -m gamst_bench.cloud --job <resolved-job.json> --out <new-private-run-directory>` to validate/print a command. Add `--execute` **on the verified GCE VM only** to run it. See [cloud launcher requirements](../infra/gcp/README.md#native-fastbench-launcher). This launches baseline or ProactiveFrame; it is not a Gamst hybrid adapter.
