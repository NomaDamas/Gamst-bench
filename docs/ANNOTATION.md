# Annotation and accounting rubric

Before test collection, write answerability, relevant event bounds, deadline, reference answer, accepted variants, critical fact IDs and negative controls. Keep the full annotation package private from adapters and pin its revision in the experiment record. Distinguish current, last-seen, missing and unknown. Do not label hidden emotions from facial appearance as ground truth.

Generate a review form with `assess-template`; pending/null fields cannot be evaluated. Review the exact first final `answer` event and the source media available at its delivery. Use a configuration-blinded rubric and two independent reviewers for ambiguous semantics; adjudicate disagreement before publishing. Preserve reviewer decisions and inter-rater agreement outside the public report if sensitive.

For each trace, set:

- `review_status`: `reviewed` for real measurements; `synthetic` only for fixtures.
- `reviewer`, `rubric_revision`, `notes`: durable review provenance and explanations.
- `correct`: answer matches the frozen acceptable answer; a fluent answer is insufficient.
- `grounded`: every substantive claim has semantically adequate evidence available at that time.
- `evidence_ids`: source input IDs actually supporting the judged answer. These are not internal plugin IDs.
- `abstained`: answer explicitly declines unsupported inference. Assess whether the task was unanswerable.
- `stale_error`: answer presents obsolete/last-seen context as current.
- `claim_count`, `unsupported_claims`: count atomic factual claims consistently, including incorrect invented details.
- `correct_facts`: subset of the task's critical fact IDs preserved in the first answer; never credit a missing answer.
- `false_alerts`: unmatched/spurious alerts over the trace. Match each alert one-to-one to annotated event windows; repeated alerts for one event are extras. This rubric count is not an implementation of SPOT's official Timeliness-F1.
- `accounting_complete`: true only after auditing all full-pipeline quantities against the rate card.
- `accounting_evidence`: measured accounting requires invoice/profiler/job-allocation artifact references. Include allocation formula, duration, tariff revision and unknown components.

`trace_sha256` binds a review to its exact trace. Editing the trace invalidates the assessment. The evaluator checks types, hashes, pair completeness, timing and citation existence; it cannot check human honesty or semantic correctness automatically.

For error/timeout/no-answer runs, mark correct/grounded false, facts/evidence empty, and annotate the failure. Do not discard failures, substitute a later answer, or mark costs zero just because usage was not returned. Independently meter failed remote calls where possible.
