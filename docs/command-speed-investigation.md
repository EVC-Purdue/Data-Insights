# Focused requested-speed versus measured-speed investigation

## Oversized-window recovery and trace identity

The tool declaration and both parameter descriptions explicitly require end minus start <=30 seconds. Runtime validation remains authoritative. Oversized requests return a matching SDK function response with an `error` object: code `window_too_large`, `requestedDurationSeconds`, `maximumDurationSeconds: 30`, concise retry guidance, `suggestedWindow` (explicit start/end or null), and `suggestionStatus` (`available` or `no_usable_overlap`). No request is silently clamped or executed. The rejected attempt consumes one of six slots and delivers no evidence IDs. Other invalid argument types retain their existing generic error.

Suggestion rule: reuse the existing finite-span overlap helper with whole-run cadence, breaking at nulls and internal gaps. In chronological order, consider each positive-duration common span, taking its first at most 30 seconds. Require a positive-duration overlap under window-local cadence too; skip candidates with insufficient cadence or overlap. Return the first qualifying candidate, otherwise explicitly return null. This conservative availability heuristic is not a tracking or fault calculation. An isolated Diagnostics instance computes candidates so rejected requests do not register evidence. No run names, timestamps, telemetry values, or bag-audit conclusions are hardcoded. The suggestion can lie outside the rejected interval, but always within the selected run's usable common coverage.

Guidance prioritizes the focused comparison over redundant whole-run summaries, asks for a valid retry when budget remains, and distinguishes request failure from unavailable data. The six-attempt limit, matching function-call IDs, original SDK content/thought signatures, strict evidence checks, and tools-disabled finalization remain intact.

Each investigation generates a UUID `analysisId`. Sanitized tool events, aggregate tool traces, finalization evidence traces, and the successful `/analyze` JSON response share it. The response field is additive; existing consumers can ignore it. No full report, raw telemetry, secret, or signature is logged. This ID identifies an investigation, not a recording or evidence object.

At the oversized-window implementation stage, 66 offline backend tests passed. Regression coverage includes actionable error serialization without evidence, a successful focused retry delivering both signals, null/gap-aware suggestions, no-overlap cases, and seven requested comparisons yielding only six budget-consuming attempts with the seventh rejected. Trace identity matches the response. Serialized synthetic example: requested duration 84 seconds, maximum 30, suggestion `{start: 0, end: 30}`; evidence count zero. No live Gemini request was made. Live recovery behavior remains unevaluated.

`command_speed_window(start, end)` is a read-only Gemini diagnostic tool costing **one** of the existing six executed diagnostic calls. Bounds must be explicit finite numbers, increasing, within the selected run, and at most 30 seconds apart. No provider/model or finalization-budget changes were made.

It reuses Python `summary` and `coverage` for both signals over exactly the same inclusive window, returning individual evidence IDs, provenance, units, counts, timestamped extrema, actual sample bounds, null counts, uncovered edges, and cadence-based internal gaps. Physical recordings use `commanded` and `speed`; compatible simulator data can use `cmd_speed` and `speed` with documented m/s units. Empty coverage has null actual bounds, even though the older summary helper retains requested bounds as its empty-window fallback. `coverage.requestedWindow` identifies the interval being assessed; `timeBasis` retains the original run clock and bounds.

The existing cadence rule is calculated on distinct timestamps **inside the requested window**: at least three spacings, gap > three times median spacing + 1e-9 s. As before, irregular sampling or too few samples can make cadence unknown or unrepresentative. Coverage lists the largest three gaps and explicit omission counts.

Availability overlap is a separate evidence record. It intersects finite-sample spans, breaking spans at nulls and cadence gaps. Unknown cadence permits isolated timestamps only. At most three overlap intervals are returned, with total/omitted counts. A coincident isolated timestamp counts as availability overlap, not evidence of sustained coverage. This is an availability heuristic, not interpolation of values, asynchronous sample pairing, or a guarantee that every moment has valid data.

No tracking error, correlation, response delay, causal inference, or acceptable-error threshold is computed. Whole-window extrema are separate observations; their difference is not a tracking-error measurement. Existing evidence delivery and strict report validation remain in force. The tool's individual summary IDs work with existing aligned-window validation; aligned summaries remain necessary but insufficient for a relationship claim.

## Semantics and audit provenance

Overview and comparison responses now include citable command-semantics evidence: `/cmd_drive data[0]` is requested linear speed in m/s **before actuator clamping**, not applied throttle or guaranteed achieved speed. The [source investigation](cmd-drive-mapping.md) establishes this contract; deployed firmware/configuration remains unverified.

The saved offline bag-audit JSON does not bind its conclusions to a bag-content digest and importer implementation fingerprint. It is therefore **not attached** to model analyses, even for identically named runs. Responses explicitly state `rawBagVerification.status = unavailable`. No name-based lookup or hardcoded recording conclusion was added. Supporting such artifacts later requires exact content/importer identity verification and a defined invalidation policy. Imported coverage is available independently; it cannot establish whether a source, logger, or importer caused a gap.

Guidance prioritizes one focused comparison within overlapping coverage when both signals exist. It requests a stated selection rationale and Python event/extremum anchors where available. Missing overlap must be reported as comparison unavailable. Ordinary extrema are not automatically faults, and missing coverage alone proves neither sensor, logging, nor importer failure.

## Offline verification on the two recordings

Reproduce from the repository root; no key or Gemini request is needed:

```powershell
.\.venv\Scripts\python.exe backend\inspect_command_speed.py `
  C:\Users\chack\Documents\AutonomousKart_Diagnostics\20260519_150616\20260519_150616_0.mcap `
  C:\Users\chack\Documents\AutonomousKart_Diagnostics\20260519_211017\20260519_211017_0.mcap
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
```

The inspection helper selects the largest absolute measured-speed extremum within common finite timestamp bounds, then takes up to five seconds on either side, clipped to those bounds. This is a repeatable investigation anchor, not a fault detector. The comparison independently checks usable coverage. Full local output: `.cache/command-speed-windows.json` (aggregate evidence, not a committed artifact).

| Run | Explicit window (s) | Requested speed | Measured speed | Selection anchor |
|---|---|---|---|---|
| `20260519_150616_0` | 3.795278406–13.795278406 | 539 finite samples; min/max 4.000 m/s | 1000 finite samples; min -0.107188 m/s at 11.855197108; max 5.077520 at 8.795278406 | Absolute measured-speed peak at 8.795278406 s |
| `20260519_211017_0` | 206.392974140–216.392974140 | 568 finite samples; min 2.064640 m/s at 206.404199185; max 4.000 at 209.910395947 | 1001 finite samples; min 0 at 206.393215739; max 4.333109 at 211.392974140 | Absolute measured-speed peak at 211.392974140 s |

150616 actual command bounds: 3.802156107–13.783611867 s; speed bounds: 3.805021185–13.795234356 s. Usable overlap: 3.805021185–13.783611867 s. Leading/trailing uncovered edges are respectively 0.006878/0.011667 s for commands and 0.009743/0.000044 s for speed. Summary IDs: `ev-ec690526119f1b7a`, `ev-c1b2fe72de95f051`.

211017 actual command bounds: 206.404199185–216.389889944 s; speed bounds: 206.393215739–216.392641483 s. Usable overlap: 206.404199185–216.389889944 s. Leading/trailing edges are respectively 0.011225/0.003084 s for commands and 0.000242/0.000333 s for speed. Summary IDs: `ev-31eaff095d638d76`, `ev-e936f9bb5460e46c`.

Both selected windows have zero nulls and zero cadence-detected internal gaps. The second recording's common finite bounds begin at 115.467506708 s, so its earlier major measurement gaps cannot be investigated against recorded speed commands. These conclusions use the current offline import; the tool still correctly states raw-bag verification unavailable to the model analysis.

At the initial focused-comparison implementation stage, 63 offline backend tests passed. New tests cover full/partial overlap, internal gaps, timestamped nulls, empty commands, disjoint coverage (including overlapping outer bounds with a gap), explicit bounded arguments, delivered evidence validation, and a seven-call mocked request executing only six comparison calls followed by tools-disabled finalization. No live Gemini evaluation was performed at that stage; see the subsequent verification below.

## Subsequent verification and commit review

The latest backend suite contains 68 offline tests, last reported passing and rerun during commit preparation. A prior live analysis, `03d68646ebea4b4eac59b159e4f429c3`, completed three successful diagnostic calls: `run_overview`, `command_speed_window` for [0,30] seconds, and `time_window_summary` for throttle in the same window. It did not exercise oversized-window recovery. That report exposed narrative citation omission and semantic guidance issues.

The subsequent complete citation validation/evidence inclusion fix has offline verification only. No live API requests were made during this review. Offline tests verify deterministic checks and evidence retention; they do not guarantee model semantic correctness. See [report evidence validation](report-evidence-validation.md).
