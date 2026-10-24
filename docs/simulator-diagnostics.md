# Simulator imports and diagnostics

This is an additive extension of the Flask/React dashboard. MCAP parsing, the Jetson collector and SQLite snapshots remain in place. No simulator submit/delete endpoint is exposed or called. No commits or pushes are needed.

## Setup

From the repository root (PowerShell):

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
# Optional: defaults to https://evc.researchviewer.org
$env:SIMULATOR_URL = 'https://evc.researchviewer.org'
.venv/Scripts/python backend/app.py
```

In another terminal:

```powershell
cd frontend
npm install
# frontend/.env.local should contain VITE_API_URL=http://127.0.0.1:5000/api
npm run dev
```

Without `VITE_API_URL`, existing mock mode remains available; simulator/AI controls are hidden. With the backend connected, choose **Load simulator jobs**, a completed job and episode, then **Import episode**. Cached runs load at backend startup from `recordings/simulator/` and can be selected offline without contacting the simulator. The cache contains original episode JSON and normalized runs, including provenance/configuration. It is ignored by Git. Corrupt entries are skipped with a startup message. Reimport refreshes that episode atomically.

The Flask process must have `OPENAI_API_KEY` and `OPENAI_MODEL` in its environment for AI. Use a model available to your project that supports Responses function calling and structured JSON output. Neither variable belongs in React or a `VITE_` variable. This app does not auto-load backend `.env` files; supply the environment before starting Flask. Do not paste credentials into source, Git, diagnostic notes, or logs. With either variable absent, imports and deterministic diagnostics work and AI returns **AI analysis not configured**.

## API additions

| Route | Behavior |
| --- | --- |
| `GET /api/simulator/jobs` | Flask reads the simulator job list |
| `GET /api/simulator/jobs/{job}/episodes` | Extracts lap and clip episode keys from the job breakdown |
| `POST /api/simulator/import` | JSON `{ "jobId": "...", "episodeId": "..." }`; reads a completed job/episode and caches locally |
| `GET /api/runs/{id}/diagnostics` | Python summaries, events, provenance, available signals and AI configuration status |
| `POST /api/runs/{id}/analyze` | Explicit AI request against an immutable selected-run snapshot |

Existing `/api/runs`, telemetry and health contracts are retained. New simulator chart fields are `steeringAngle`, `lateralAcceleration`, and `simPosition`. Legacy PWM, sensor-X acceleration and GPS series are empty for simulator runs. `commanded` retains the controller panel's `target`/`actual` shape. Only valid same-time values are paired; nulls stay null.

Simulator HTTP is GET-only with fixed backend-configured base URL, validated identifiers, no redirects, 5-second connect/15-second read timeouts, a checked 30-second transfer budget and 32 MiB response limit. Two sequential reads are needed for import. Errors are returned as JSON; local cache writes must succeed before a run is accepted.

## Data and evidence semantics

The internal `diagnostic` object has `schemaVersion: 1`, metadata, measurements, upstream metrics, outcome and upstream events. A measurement contains `unit`, `kind`, `source`, and `samples: [{time, value}]`. Metrics carry value, unit, definition/source and evaluation-window provenance. Each calculated summary/event has a stable evidence ID and source, units, time window and threshold provenance (or explicitly no threshold). Existing recorded/live runs receive this format on demand without changing their stored telemetry.

The simulator public API rounds and decimates telemetry to roughly 20 Hz; this is not the original full-rate log. Unknown signal arrays are retained with unknown units/classification; nested fields such as plan costs remain in the original cached response. Available engine/tier versions, recipe source ref/commit, parameters, timestamps and scenario are retained. Missing commits or resolved configuration files are not invented; the API does not expose every configuration artifact.

`log.t` is simulator time minus `outcome.handoff_t`. Negative values are retained and plotted. When that field is absent, upstream uses zero; our time basis becomes `simulator_time_handoff_unknown`. The synthetic API handoff event at zero does **not** establish the true handoff. There is no alignment to wall-clock time or MCAP/live clocks. `date` is the job finish time, not a per-sample timestamp. Run duration is the available telemetry span.

Simulator speed, position and wheel angle are simulation ground truth; commands are separate. `ay_mps2` is upstream filtered body lateral acceleration, not the dashboard's existing IMU X-axis signal. Viewer yaw rate is already degrees/second. `loc_err` is estimator error against simulation reference truth; zeros before the first odometry can be upstream placeholders. No real-world localization error is calculated for MCAP/Jetson without reference truth. Live analysis uses a snapshot of the retained five-minute window.

Numeric summaries use Python and finite samples only, with sample-weighted means/RMS and timestamped extrema. Missing values are counted and never interpolated. Distance is unavailable if the simulator speed series has nulls. It otherwise integrates absolute forward speed, not a GPS trajectory length.

Independent event detection is intentionally small: autonomous viewer samples exceeding the **returned** `lat_limit.envelope`, and explicit missing samples. A missing threshold disables lateral detection. Nulls, non-autonomous samples and gaps over 0.15 seconds break a lateral event; that gap bound is an adapter continuity heuristic for 20 Hz viewer data, not a simulator safety threshold. There is no generic arbitrary steering/acceleration threshold. Simulator failure labels and full-rate unsafe intervals are separately marked as upstream annotations, not independent diagnoses. The outcome check exposes the supplied label alongside our independent result and explicitly says these cannot validate a root cause. No detected events is not evidence of safety. Full localization/command timeout, footprint, spin and recovery rules are not reproduced with incomplete/decimated data. UI event output is capped at 80 and reports truncation.

## Agent bounds and report validation

The official OpenAI Python SDK uses `AsyncOpenAI.responses.create`, strict function schemas and structured JSON reports. There are four tools: metadata, available signals, time-window summaries and detected events. Tools have no run selector, network, shell, vehicle control or simulator mutation capability. Dispatch validates exact argument keys, known signal names and finite ordered time bounds.

Limits: six tool calls, at most seven Responses requests, 3,500 output tokens/request, 48,000 serialized history characters, 16,000 characters/tool output, 20-second SDK timeout with retries disabled, and 60 seconds for the whole cancellable loop. One AI request is allowed at a time per Flask process. Large tool outputs return a limit message; they are not silently treated as complete data. Reasoning items and encrypted reasoning content are preserved across stateless calls (`store=False`). Imported notes/log text are explicitly untrusted data, never instructions. The model chooses the tools; there is no canned “AI analysis.”

Pydantic validates report fields, finding classifications and evidence references. Returned findings must cite evidence actually delivered to the model; empty measurement windows cannot support findings. An upstream label cannot be classified as independent observation. Supporting evidence is attached server-side, not generated by the model. Hypotheses include evidence and uncertainty; insufficient data is a valid outcome. Schema/reference validation cannot prove a model's prose or causal inference is correct: the displayed evidence remains the review basis. API errors/refusals/incomplete or invalid outputs return an error, not a substitute report. SDK exception bodies are not returned or logged by the application.

## Source review and licensing

Reviewed AutonomousSimulator revision `a9bfce0583e337b11f414e6057c1eab69182d34e`:

- [web/app.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/web/app.py): viewer API, units, filtering/decimation, handoff subtraction.
- [runner/store.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/runner/store.py): episode cache/index, job breakdown and outcome availability.
- [harness/metrics.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/harness/metrics.py): lateral envelope, filtering, localization and evaluation masks.
- [harness/failures.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/harness/failures.py): failure criteria and configurable thresholds.

The upstream LICENSE is GPL-3.0; this repository is MIT. No upstream implementation was copied or bundled. The adapter consumes API data and independently implements simple summaries and comparisons, referencing upstream definitions. The adapter reference revision identifies the source reviewed, not a claim that the deployed simulator uses that exact revision; the job's reported engine version is stored separately.

OpenAI implementation references: [function calling](https://developers.openai.com/api/docs/guides/function-calling) and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Verification and real AI smoke test

Automated tests deliberately use synthetic telemetry fixtures and mocked model replies:

```powershell
.venv/Scripts/python -m unittest discover -s backend/tests -v
cd frontend
npm run build
```

A real simulator import was verified on 2026-10-24 (UTC), job `20261015-103213-ls-act`, episode `1a003a065b58564c508b7d4dd47a69f7120eb0f9dca77888b9518b7ac9d22438`: Flask import HTTP 200, 368 speed samples, 24 signals, successful offline cache reload. Outcome metadata was empty; the job breakdown supplied `localization_lost`. The adapter correctly reported unknown handoff time and label-only evidence. No simulator jobs were submitted, changed or deleted.

Verification also passed 35 backend tests and the production frontend build (Vite reports a bundle-size advisory). The checked-in real MCAP `20260519_150616_0.mcap` imported successfully: 84.750006743 seconds, 8,475 speed samples, with telemetry and deterministic diagnostic routes both returning HTTP 200.

For a **real AI smoke test**, distinct from unit tests:

1. Supply `OPENAI_API_KEY` securely to the backend process and set `OPENAI_MODEL` to an accessible Responses/structured-output model. Restart Flask. Keep the key out of frontend configuration.
2. Start the connected frontend. Import the completed episode above (or select its local cached run).
3. Click **Deterministic diagnostics**. Verify its time basis, source, missing values and simulator-label classification. Confirm “AI analysis not configured” is absent.
4. Click **Analyze Run** once. This makes billable OpenAI requests with diagnostic data from this run. Wait up to 60 seconds. Do not treat the deterministic display as the AI result.
5. Verify the returned panel says `OpenAI Responses API`, identifies the configured model and a positive tool-call count, and displays a validated report or explicit insufficient-data result. Open each evidence item and compare its measurements/time window with deterministic diagnostics. `localization_lost` must be identified as an existing simulator label unless independently supported observations are separately stated.
6. Change runs during analysis and confirm stale results do not appear on the new run. Live refresh alone must not initiate AI requests. Stop/restart Flask without network and confirm the simulator run still opens locally (AI itself requires network).
7. Remove backend AI configuration and restart. **Analyze Run** should show **AI analysis not configured** while import and deterministic diagnostics remain usable.

The implementation session had no configured backend AI credentials/model, so no real OpenAI end-to-end result is claimed. Automated SDK/API mocks are only contract/failure-path checks. Live Jetson hardware was not available; existing health/telemetry behavior was checked with a synthetic live snapshot.
