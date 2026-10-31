# Simulator imports and diagnostics

This is an additive extension of the Flask/React dashboard. MCAP parsing, the Jetson collector and SQLite snapshots remain in place. No simulator submit/delete endpoint is exposed or called. No commits or pushes are needed.

## Setup

From the repository root (PowerShell):

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
# Optional: defaults to https://evc.researchviewer.org
$env:SIMULATOR_URL = 'https://evc.researchviewer.org'
.venv\Scripts\python.exe backend\app.py --port 5000
```

In another terminal:

```powershell
cd frontend
npm install
# frontend/.env.local should contain VITE_API_URL=http://127.0.0.1:5000/api
$env:VITE_API_URL = 'http://127.0.0.1:5000/api'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Without `VITE_API_URL`, existing mock mode remains available; simulator/AI controls are hidden. With the backend connected, choose **Load simulator jobs**, a completed job and episode, then **Import episode**. Cached runs load at backend startup from `recordings/simulator/` and can be selected offline without contacting the simulator. The cache contains original episode JSON and normalized runs, including provenance/configuration. It is ignored by Git. Corrupt entries are skipped with a startup message. Reimport refreshes that episode atomically.

The connected dashboard opens the real kart recordings view by default. Select a local MCAP bag and use its **Run diagnostics** panel to calculate deterministic evidence or explicitly request **Analyze Run** for an AI review of that selected recording. Simulator runs remain available at `?source=simulator`; the same analysis endpoint supports selected simulator and live runs. AI does not run automatically when changing recordings.

The default AI provider is the hosted Gemini API. `AI_PROVIDER=gemini` is the only supported provider in this configuration; there is no fallback to Ollama or a paid provider. Configuration belongs in the Flask process environment, never frontend/VITE variables. The backend does not load `.env` files.

- `GEMINI_API_KEY` is required by the backend and is never sent to React.
- `GEMINI_MODEL` selects the model (default `gemini-3.5-flash-lite`). Choose a project/key with free-tier access and do not link a billing account if you want free-tier-only API use. A free-tier quota can still be exhausted; the app reports that and does not switch providers.
- `GEMINI_REQUEST_TIMEOUT_SECONDS=180` controls an individual request (1 to 1,800 seconds); `AI_ANALYSIS_TIMEOUT_SECONDS=300` caps the entire analysis loop (1 to 3,600 seconds).

The selected model is documented by Google as supporting function calling and structured outputs, with free-tier pricing listed for input and output. Free-tier limits can vary by project and change over time. See [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) and [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).

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

The Gemini adapter uses Google's official `google-genai` Python SDK and the hosted Gemini API. The bounded loop disables SDK automatic function execution, lets the model choose among six read-only tools (overview, metadata, signals, coverage, events, and window summaries), validates arguments in Python, dispatches them only against the selected run and returns tool results to the model. A separate request uses Gemini's JSON-schema structured output for the final report; Pydantic and server-side evidence-reference validation gate the displayed report. Tools have no run selector, network, shell, vehicle control or simulator mutation capability. Dispatch validates exact argument keys, known signal names and finite ordered time bounds.

Limits: six tool calls, bounded by a 48,000-character serialized context and 16,000 characters per tool result. Requests have configurable per-request and overall timeouts, with SDK retries disabled. One AI request is allowed at a time per Flask process. Large tool outputs return a limit message; they are not silently treated as complete data. Imported notes/log text are explicitly untrusted data, never instructions. The model chooses the tools; there is no canned AI analysis and no provider fallback.

Pydantic validates report fields, finding classifications and evidence references. Returned findings must cite evidence actually delivered to the model; empty measurement windows cannot support findings. An upstream label cannot be classified as independent observation. Supporting evidence is attached server-side, not generated by the model. Hypotheses include evidence and uncertainty; insufficient data is a valid outcome. Schema/reference validation cannot prove a model's prose or causal inference is correct: the displayed evidence remains the review basis. API errors/refusals/incomplete or invalid outputs return an error, not a substitute report. SDK exception bodies are not returned or logged by the application.

## Source review and licensing

Reviewed AutonomousSimulator revision `a9bfce0583e337b11f414e6057c1eab69182d34e`:

- [web/app.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/web/app.py): viewer API, units, filtering/decimation, handoff subtraction.
- [runner/store.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/runner/store.py): episode cache/index, job breakdown and outcome availability.
- [harness/metrics.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/harness/metrics.py): lateral envelope, filtering, localization and evaluation masks.
- [harness/failures.py](https://github.com/EVC-Purdue/AutonomousSimulator/blob/a9bfce0583e337b11f414e6057c1eab69182d34e/harness/failures.py): failure criteria and configurable thresholds.

The upstream LICENSE is GPL-3.0; this repository is MIT. No upstream implementation was copied or bundled. The adapter consumes API data and independently implements simple summaries and comparisons, referencing upstream definitions. The adapter reference revision identifies the source reviewed, not a claim that the deployed simulator uses that exact revision; the job's reported engine version is stored separately.

Gemini implementation references: [function calling](https://ai.google.dev/gemini-api/docs/function-calling), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), and [official Python SDK](https://ai.google.dev/gemini-api/docs/libraries).

## Gemini setup and real smoke test

Automated tests use clearly labeled synthetic telemetry and mocked Gemini SDK responses; they are not a real model check. The previously verified simulator episode is cached under run ID `sim-e221c1bfeb360810fc89c9cf`.

Install the backend dependencies after updating this integration:

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Create a Gemini API key in AI Studio using a project that remains on the free tier. To enter it into the current PowerShell process without echoing it, run these commands in terminal 1 from the repository root. The key stays out of chat, source code and Git; it is present only in the Flask process environment and inherited by the backend process.

```powershell
Set-Location 'C:\Users\chack\Documents\Data-Insights'
$secureKey = Read-Host 'Gemini API key (hidden)' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
Remove-Variable secureKey
$env:AI_PROVIDER = 'gemini'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'
$env:GEMINI_REQUEST_TIMEOUT_SECONDS = '180'
$env:AI_ANALYSIS_TIMEOUT_SECONDS = '300'
.venv\Scripts\python.exe backend\app.py --port 5000
```

In terminal 2, start the existing frontend:

```powershell
Set-Location 'C:\Users\chack\Documents\Data-Insights\frontend'
$env:VITE_API_URL = 'http://127.0.0.1:5000/api'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open the dashboard's cached simulator run `sim-e221c1bfeb360810fc89c9cf` (episode prefix `1a003a065b`) and click **Analyze Run** once. Check the report response/provider identifies Gemini and the configured model, and `toolCalls` is greater than zero. Compare every attached evidence ID to the deterministic diagnostics for that run: its numeric values, units, source and timestamps must match the Python-generated summary/event. This episode has unknown handoff time, so evidence must retain simulator-relative time. Its `localization_lost` is an existing simulator label, not independent root-cause evidence. This smoke test uses the hosted Gemini free-tier API; it is separate from mocked automated tests. If quota is exhausted, the dashboard reports a quota error and does not fall back.

Backend verification:

```powershell
Set-Location 'C:\Users\chack\Documents\Data-Insights'
.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```


TODO:
1. Cost Function Mapping
2. Change Arrow to match kart and be realistic


Integration verified against Google model/pricing documentation on 2026-10-28. SDK Content and binary thought signatures are retained unchanged across turns; a separate base64 JSON representation is used only for context accounting. Parallel tool replies retain call IDs. The user subsequently confirmed successful real Gemini analyses. Offline regressions do not independently establish live API success or diagnostic quality; no additional live requests were made while preparing this commit.
