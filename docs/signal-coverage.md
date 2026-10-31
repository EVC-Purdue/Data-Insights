# Diagnostic signal coverage

`run_overview` combines compact metadata/time bounds and coverage evidence in one diagnostic call. It prioritizes speed, acceleration/lateral acceleration, steering, throttle, and speed commands, followed by other signals (up to 12). Omitted signal names are explicit; `signal_coverage(signal)` retrieves any individual signal. Both tools are read-only and use the same six-call budget. Existing metadata, signal-list, event, and numeric-summary tools remain available.

Each coverage record has a stable evidence ID, signal name, unit, classification, provenance, and time basis. It includes first/last recorded timestamps, first/last finite-value timestamps, leading/trailing uncovered intervals relative to the run, sample/null/invalid counts, and internal timestamp-gap evidence. Physical recorded-run bounds include the bag duration and its zero log-time origin, rather than treating the shortest signal as the whole run. Live snapshots retain their own timestamp range; simulator bounds use the imported time basis.

## Cadence rule

Sort distinct finite timestamps and take the median of positive adjacent spacings. At least three spacings are required; otherwise cadence and the gap threshold are unknown. Flag an internal gap when its spacing exceeds three times that median plus a 1e-9-second floating-point tolerance. Report both boundary sample timestamps and the full interval between them; do not invent a count of missing samples or interpolate. Gap totals include every detected gap; the largest three intervals are included in the tool response (ties ordered by start time), with an explicit truncation flag. This bounds tool context while identifying useful focused windows.

Leading/trailing intervals are exact timestamp spans, with no cadence tolerance: a few milliseconds of endpoint skew in asynchronous data is not a failure. An empty series has no first/last timestamp and reports the entire known run interval as uncovered, rather than overlapping leading/trailing intervals. A series of null values has timestamps but no finite-value coverage. Nulls/nonfinite values at present timestamps are counted separately from absent timestamps. An internal null does not itself create a timestamp gap; the existing missing-data event also identifies the span of explicit missing values.

This is an observed-cadence heuristic, not a declared sampling contract. Irregular/event-driven signals or extended widespread loss can make the median misleading. A gap may reflect recording, import/filtering, or availability issues; it does not establish sensor failure. Coverage describes the samples actually exposed by the importer, not every raw bag message. For example, the physical IMU importer filters invalid covariance/nonfinite acceleration values, so filtered samples cannot be relabeled as explicit nulls after import.

## Investigation quality

Instructions request the overview first, then prioritize measurement and available command evidence and focused windows within the remaining calls. Steering/throttle explanations require inspection of those signals; coverage alone cannot explain command behavior. If commands cannot be inspected, the report must say the explanation is unassessed. Extrema alone are observations, not faults. No rule triggered is not proof that no anomaly exists. Gaps and coverage limits belong in the report, without unsupported sensor-failure claims.

Window summaries now include Python-calculated `meanAbsolute`, RMS, and positive/negative/zero sample counts alongside signed mean and extrema. All are sample-weighted, not time-weighted distance calculations. Forward and reverse speeds can cancel in signed mean while showing substantial speed magnitude. Prompt guidance does not mechanically prove every prose claim; strict report schema and evidence-ID/delivery/classification checks remain in force.

## Verification

Offline tests cover partial coverage with zero nulls, cadence-based internal gaps, threshold boundaries, insufficient cadence, empty versus all-null signals, evidence delivery checks, and forward/reverse speed cancellation. Existing six-call budget, provider schema, binary-signature, and report-validation tests also pass (48 tests total).

An offline import of physical recording `20260519_150616_0` found:

- Run end / last speed sample: 84.750006743 s.
- Last acceleration sample: 58.519715701 s.
- Trailing acceleration interval: 26.230291042 s, despite zero explicit null values.
- Steering and throttle each have three internal gaps under the documented rule; these are coverage observations, not fault diagnoses.
- The physical-run overview serializes to about 8 KB, below the existing 16 KB tool-result limit.

No real Gemini request was made for this change. Restart Flask and analyze the recording again to assess the updated model response; offline calculations and mocked tests do not verify model interpretation.

## Finalization and diagnostic trace

Offline inspection of the exact `run_overview` JSON for `20260519_150616_0` measured 8,030 characters, below the 16,000-character tool limit. Acceleration evidence `ev-e8c3840b63661f99` contains the trailing interval 58.519715701–84.750006743 s (26.230291042 s) and passes the original delivery filter. The new filter matches actual evidence objects structurally, rather than accepting IDs merely mentioned in text. A saved local inspection artifact is `.cache/overview-20260519_150616.json`. This confirms the current delivery path when the overview is called, not what happened in an earlier untraced live request.

Before the one final structured request, Python computes significant coverage limitations directly from the selected run. An interval is significant at >= max(1 second, 5% of run duration, 3 estimated cadence intervals); explicit invalid values and empty/all-invalid signals are also included. Up to eight signal limitations, largest intervals first, are supplied as compact evidence records. Omission counts are explicit; the context is capped at 12,000 characters and still subject to the overall context cap. This is deterministic finalization preparation, not another requested diagnostic-tool call. Only the evidence records actually included become delivered IDs. The six-call execution budget and single bounded finalization remain intact.

For the inspected recording, finalization includes the acceleration gap and the empty imported `commanded` signal. It explicitly instructs inclusion of limitations in summary/uncertainty. Empty import data does not establish that the source bag lacks a topic: topic inventory has not been checked by the agent's tools.

Window evidence now records the requested bounds separately from actual sample bounds. Eligible cross-signal windows must share explicit start/end bounds, be narrower than the run, contain samples, and overlap in observed time. Local validation rejects multi-signal hypotheses whose cited window summaries lack such an aligned group. Whole-run extrema support separate observations only. Aligned aggregate summaries are necessary but insufficient to prove correlation or causality; no correlation calculation is implemented. Free-form prose still requires model compliance with instructions and human review; these structural checks do not prove every narrative claim.

Enable backend-only trace before restarting Flask:

```powershell
$env:GEMINI_DIAGNOSTIC_TRACE = '1'
```

Tool events include allowlisted names/arguments, outcome, successful-execution flag, and delivered evidence IDs. Only known signal names and bounded finite numeric time arguments are logged; unexpected names/values are withheld. No raw results, prompts, credentials, headers, signatures, or provider text are logged. Trace entries are capped at 24 and evidence IDs at 32 per entry, with omission counts. A final summary distinguishes requested calls, budget-consuming attempts (including invalid calls), and successful dispatches. `output_limit` means dispatch succeeded but the result/evidence was not delivered. Events emit immediately even if a subsequent request fails. Finalization logs only its coverage evidence IDs, context length, and omission count. Disable by removing the environment variable.

Verification after this update: 52 offline tests pass, including structural delivery, oversized tool output, requested-versus-executed tracing, computed finalization gaps, and rejection of unaligned cross-signal hypotheses. No live Gemini verification was performed.
