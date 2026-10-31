# Opt-in Gemini diagnostics

`backend/diagnose_gemini.py` uses the installed google-genai SDK, `GEMINI_API_KEY`, and the same `GEMINI_MODEL`/default as the agent. It does not load key files or inspect another process's environment. It requires `--live`; unit tests do not run live requests.

Stages run sequentially and stop at the first failure:

1. Minimal text.
2. Minimal structured JSON.
3. The production `provider_report_schema()` JSON schema, followed by unchanged strict local `Report` and evidence validation.
4. One forced diagnostic function call and its matching response, followed by text.
5. Two forced diagnostic tool turns on synthetic speed data, followed by the same `finalize_report` function used in production. Original SDK Content and thought signatures are retained. Evidence IDs come from Python diagnostics.
6. Only with `--run-id`: POST one existing recording to the running Flask `/api/runs/<id>/analyze` endpoint, after all synthetic stages pass. Flask must have the same model and its own backend API-key environment. The probe checks the returned provider, model, budget, and local report schema; Flask performs evidence validation. Report bodies are not printed.

There are no automatic retries. Each SDK request is capped at 30 seconds (or the shorter configured timeout); each synthetic stage is capped at 90 seconds (or the shorter configured total budget). The endpoint has a timeout of the configured analysis budget plus 15 seconds. The normal production six-call budget and finalization remain unchanged.

## Failure logging

The dashboard's generic `gemini_request_error` is the fallback for SDK API errors other than HTTP 401/403 (authentication), 404 (model/resource), 429 or RESOURCE_EXHAUSTED (quota), and >=500 (service). For example, HTTP 400 INVALID_ARGUMENT or 422 maps to that message. It does not identify a specific schema failure.

Backend logs now contain a JSON `Gemini diagnostic` with the exact request phase (`investigation_initial`, `investigation_followup`, or `structured_finalization`), HTTP status, numeric provider code, allowlisted provider status, and a fixed explanation classified from the provider message. Unrecognized messages are withheld. No raw provider text, exception repr, headers, credentials, telemetry, prompts, or thought signatures are logged. Unknown status/phase strings are withheld too. Detailed diagnostics are not added to the API response.

## Current findings (2026-10-31)

The user initially confirmed live stages a/b passed and stage c (`report_schema`) failed with HTTP 400 INVALID_ARGUMENT, isolating the original Report request rather than a specific keyword. After the provider schema was simplified, the user confirmed that real Gemini analyses complete. Those user-run live checks are distinct from the offline regression suite; the exact schema-reduction result and individual d/e probe outputs were not supplied. No additional live requests were made while preparing this commit.

The installed SDK is 2.33.0; configured default is `gemini-3.5-flash-lite`. A definite schema-format mismatch was corrected: `parameters_json_schema` used OpenAPI `nullable: true`; JSON Schema now uses `type: ["number", "null"]` for optional time bounds. A real SDK request-serialization regression uses an intercepted HTTP transport with synthetic data; it does not contact Gemini.

Google's [structured output documentation](https://ai.google.dev/gemini-api/docs/structured-output#json-schema-support) specifies null type unions and documents [schema complexity limitations](https://ai.google.dev/gemini-api/docs/structured-output#limitations), including 400 INVALID_ARGUMENT for excessive constrained-decoding states. Our Report has nested bounded arrays, so complexity remains a possible explanation for the original rejection; a specific rejected construct has not been proven. Production now sends a separate, inlined JSON schema through `response_json_schema`: type, properties, required, items, and enum only. All local Pydantic constraints and evidence validation remain unchanged. Count/length constraints, extra-field rejection, and definitions are not sent as provider constraints. Text instructions still describe local limits. [Function calling documentation](https://ai.google.dev/gemini-api/docs/function-calling) describes matching tool replies and preserving thought signatures. This probe uses the installed SDK's generate_content API, rather than migrating APIs based on newer Interactions examples in the docs.

## Run locally

Restart Flask with the updated backend, existing Gemini environment, and recordings:

```powershell
Set-Location 'C:\Users\chack\Documents\Data-Insights'
.venv\Scripts\python.exe backend\app.py --data-dir 'C:\Users\chack\Documents\AutonomousKart_Diagnostics' --port 5000
```

In another PowerShell terminal, enter the key privately and use the same model as Flask (the default shown below). The optional real-recording stage sends actual diagnostic data to Gemini through Flask only after the synthetic stages pass:

```powershell
Set-Location 'C:\Users\chack\Documents\Data-Insights'
$secureKey = Read-Host 'Gemini API key (hidden)' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
Remove-Variable secureKey
$env:AI_PROVIDER = 'gemini'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'
try {
    .venv\Scripts\python.exe backend\diagnose_gemini.py --live --run-id 20260519_150616_0
} finally {
    Remove-Item Env:\GEMINI_API_KEY
}
```

Omit `--run-id` for synthetic stages only. Share only the sanitized diagnostic line and PASS/FAIL stage, never keys or raw SDK responses. If a stage fails, later stages and the recording request are skipped; this does not constitute a verified production fix.

## Bounded schema reduction

Add `--reduce-schema` to the existing `--live --run-id 20260519_150616_0` command. It tries at most four variants, stopping at the first accepted, locally valid response:

1. Original Report through `response_schema` (reproduces the rejected request).
2. Remove only array count limits from that schema.
3. Remove array counts and string lengths.
4. The simple production `response_json_schema`.

Only HTTP 400 INVALID_ARGUMENT advances to the next reduction. Quota, authentication, transport, timeout, and local validation failures stop the probe. A successful reduction then runs the normal a-e stages against the production schema, and finally the optional recording endpoint. No production retries or schema fallbacks were added. A difference in acceptance narrows the culprit to a removed group; it does not prove which individual field caused it.

The SDK's exact request was inspected with an intercepted HTTP transport and a synthetic key. The original `generationConfig.responseSchema` included `max_items`, `min_items`, `max_length`, `min_length`, `additional_properties`, and SDK-generated `property_ordering`. The new wire request is `generationConfig.responseJsonSchema`, with only the intended JSON shape and enums. This serialization check is offline, not proof of Gemini acceptance.

Sanitized diagnostics now include allowlisted `schema_keywords` (both camelCase and snake_case recognized) and `schema_fields` from our Report/Finding/Cause models. Unknown field names, full arbitrary provider paths, values, and raw messages are never printed. This can expose relevant `maxItems` / `evidence_ids` hints without exposing telemetry or secrets.
