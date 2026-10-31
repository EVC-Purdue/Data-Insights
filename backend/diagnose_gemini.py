"""Explicitly opt-in, sequential LIVE Gemini probe. Never imported by unit tests.

Run with --live; optionally --run-id ID after starting Flask with the same model.
Only the optional last stage sends an existing recording through Flask analysis.
"""
import argparse
import asyncio
import json
import logging
import re
from urllib.parse import quote, urlparse

import httpx
from google import genai
from google.genai import types

import agent
from diagnostics import Diagnostics


def synthetic_run():
    return {'id': 'synthetic-gemini-probe', 'source': 'recording', 'date': None,
            'telemetry': {'speed': [{'time': 0, 'value': 1}, {'time': 1, 'value': 2}]}}


def config(**kwargs):
    return types.GenerateContentConfig(temperature=0, max_output_tokens=2500,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True), **kwargs)


REPORT_PROMPT = ('Synthetic diagnostic: no evidence is available. Return an insufficient_data report, '
                 'empty observed_issues and possible_causes, a short nonempty summary, '
                 'one nonempty uncertainty string and empty recommended_next_checks. ' + agent.REPORT_GUIDANCE)


def schema_reductions():
    def without(node, omitted):
        if isinstance(node, dict):
            return {key: without(value, omitted) for key, value in node.items() if key not in omitted}
        if isinstance(node, list):
            return [without(value, omitted) for value in node]
        return node
    full = agent.Report.model_json_schema()
    return [
        ('original Report via response_schema', {'response_schema': agent.Report}),
        ('remove array count limits only', {'response_schema': without(full, {'minItems', 'maxItems'})}),
        ('remove count and string length limits', {'response_schema': without(full, {'minItems', 'maxItems', 'minLength', 'maxLength'})}),
        ('simple production JSON schema', {'response_json_schema': agent.provider_report_schema()}),
    ]


async def reduce_schema(client, model, timeout):
    """At most four synthetic requests; only schema 400s permit the next trial.

    This diagnostic mode is not a production retry/fallback. A PASS narrows the
    rejection to removed constraints as a group, not an individual field.
    """
    for label, schema in schema_reductions():
        try:
            response = await asyncio.wait_for(client.models.generate_content(model=model, contents=REPORT_PROMPT,
                config=config(response_mime_type='application/json', **schema)), timeout=timeout)
        except agent.errors.APIError as exc:
            detail = agent.sanitized_failure(exc, 'schema_reduction')
            print('FAIL reduction ' + label + ': ' + json.dumps(detail), flush=True)
            if exc.code != 400 or exc.status != 'INVALID_ARGUMENT':
                return False
            continue
        except Exception as exc:
            print('FAIL reduction ' + label + ': ' + json.dumps(agent.sanitized_failure(exc, 'schema_reduction')), flush=True)
            return False
        try:
            agent.validate_report(require_text(response), Diagnostics(synthetic_run()), set())
        except Exception:
            print('FAIL reduction ' + label + ': response failed strict local validation; stopped.', flush=True)
            return False
        print('PASS reduction ' + label + ' (provider accepted and strict local validation passed).', flush=True)
        return True
    return False


def require_text(response):
    if any(p.function_call is not None for p in agent._response_parts(response)):
        raise agent.AnalysisError('Unexpected function call', 'probe_protocol')
    if not isinstance(response.text, str) or not response.text.strip():
        raise agent.AnalysisError('Empty response', 'probe_empty')
    return response.text


async def tool_turn(client, model, history, diagnostic, name, phase):
    response = await agent.generate_content(client, phase=phase, model=model, contents=history,
        config=config(tools=[types.Tool(function_declarations=agent.tools())],
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                mode='ANY', allowed_function_names=[name]))))
    calls = [p.function_call for p in agent._response_parts(response) if p.function_call is not None]
    # A diagnostic probe is intentionally narrower than the production loop.
    if len(calls) != 1 or calls[0].name != name:
        raise agent.AnalysisError('Expected exactly one requested function', 'probe_protocol')
    call = calls[0]
    result = diagnostic.dispatch(call.name, call.args)
    if not isinstance(result, dict):
        result = {'result': result}
    history.append(response.candidates[0].content)  # untouched SDK parts/signatures
    history.append(types.Content(role='user', parts=[types.Part(function_response=types.FunctionResponse(
        name=call.name, id=call.id, response=result))]))
    return set(diagnostic.evidence)


async def probe(args):
    try:
        key, model, request_timeout, total_timeout = agent._configuration()
    except agent.AnalysisError:
        print('BLOCKED: set GEMINI_API_KEY and Gemini configuration in this process. No live requests made.')
        return 2
    safe_model = model if re.fullmatch(r'gemini-[a-zA-Z0-9._-]{1,80}', model) else '(configured model name withheld)'
    print(f'LIVE SDK={genai.__version__} model={safe_model}; synthetic stages; retries=0', flush=True)
    options = types.HttpOptions(timeout=int(min(request_timeout, 30) * 1000),
                                retry_options=types.HttpRetryOptions(attempts=1))
    async with genai.Client(vertexai=False, api_key=key, http_options=options).aio as client:
        if getattr(args, 'reduce_schema', False):
            if not await reduce_schema(client, model, min(total_timeout, 90)):
                print('Schema reductions failed; stages a-e and real recording were not run.')
                return 1
        async def text_stage():
            require_text(await agent.generate_content(client, phase='minimal_text', model=model,
                contents='Reply with OK.', config=config()))

        async def json_stage():
            response = await agent.generate_content(client, phase='minimal_json', model=model,
                contents='Return a JSON object with ok equal to true.', config=config(
                    response_mime_type='application/json', response_json_schema={
                        'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}))
            if json.loads(require_text(response)) != {'ok': True}:
                raise agent.AnalysisError('Unexpected minimal JSON', 'probe_validation')

        async def report_stage():
            response = await agent.generate_content(client, phase='report_schema', model=model,
                contents=REPORT_PROMPT,
                config=config(response_mime_type='application/json', response_json_schema=agent.provider_report_schema()))
            agent.validate_report(require_text(response), Diagnostics(synthetic_run()), set())

        async def single_tool_stage():
            history = [types.Content(role='user', parts=[types.Part(text='Call run_metadata once for this synthetic run.')])]
            await tool_turn(client, model, history, Diagnostics(synthetic_run()), 'run_metadata', 'single_tool')
            history.append(types.Content(role='user', parts=[types.Part(text='Acknowledge the metadata with a short text response. No more tools.')]))
            require_text(await agent.generate_content(client, phase='tool_response', model=model, contents=history, config=config()))

        async def multi_turn_stage():
            run = synthetic_run()
            diagnostic = Diagnostics(run)
            history = [types.Content(role='user', parts=[types.Part(text='Call run_metadata once for this synthetic run.')])]
            await tool_turn(client, model, history, diagnostic, 'run_metadata', 'multi_turn_tool')
            history.append(types.Content(role='user', parts=[types.Part(text='Call time_window_summary for speed, start null, end null.')]))
            evidence = await tool_turn(client, model, history, diagnostic, 'time_window_summary', 'multi_turn_tool')
            await agent.finalize_report(run, client, model, diagnostic, history, evidence, 2)

        for name, stage in [('a minimal text', text_stage), ('b minimal JSON', json_stage),
                            ('c production Report schema + strict local validation', report_stage), ('d function call/response', single_tool_stage),
                            ('e multi-turn + actual finalization', multi_turn_stage)]:
            try:
                await asyncio.wait_for(stage(), timeout=min(total_timeout, 90))
            except Exception as exc:
                # Request failures already emit allowlisted details via agent.
                cause = exc.category if isinstance(exc, agent.AnalysisError) else agent.sanitized_failure(exc, 'client_setup')['explanation']
                print(f'FAIL {name}: {cause}. Stopped; see sanitized backend diagnostic above.', flush=True)
                return 1
            print(f'PASS {name}', flush=True)

    if args.run_id:
        try:
            # No key is sent to Flask. It uses its own backend environment.
            async with httpx.AsyncClient(timeout=min(total_timeout + 15, 3615), trust_env=False) as http:
                response = await http.post(args.endpoint.rstrip('/') + '/api/runs/' + quote(args.run_id, safe='') + '/analyze')
            if response.status_code != 200:
                print(f'FAIL real recording endpoint: HTTP {response.status_code}; consult sanitized Flask backend log. Response body withheld.')
                return 1
            result = response.json()
            if result.get('model') != model or result.get('provider') != 'Gemini API' or not 1 <= result.get('toolCalls', 0) <= 6:
                raise ValueError('Unexpected endpoint contract/model')
            agent.Report.model_validate({k: v for k, v in result['report'].items() if k != 'evidence'})
            print('PASS real recording through existing analysis endpoint (live Gemini); report/telemetry withheld.')
        except Exception:
            print('FAIL real recording endpoint: connectivity or response validation; details withheld.')
            return 1
    else:
        print('SKIPPED real recording: supply --run-id to opt in after synthetic stages pass.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Explicitly authorize bounded hosted Gemini requests')
    parser.add_argument('--run-id', help='Existing physical run ID to analyze only after all synthetic stages pass')
    parser.add_argument('--reduce-schema', action='store_true', help='Up to four synthetic schema variants before normal stages; only 400 INVALID_ARGUMENT permits a reduction')
    parser.add_argument('--endpoint', default='http://127.0.0.1:5000')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live is required; no API requests were made')
    endpoint = urlparse(args.endpoint)
    if endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', 'localhost') or endpoint.username or endpoint.password or endpoint.path not in ('', '/') or endpoint.query or endpoint.fragment:
        parser.error('--endpoint must be a plain local Flask HTTP origin')
    logging.basicConfig(level=logging.WARNING, format='%(message)s')
    # Suppress SDK/transport loggers; only our allowlisted diagnostics are emitted.
    for name in ('google', 'httpx', 'httpcore'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        return asyncio.run(probe(args))
    except Exception as exc:
        print('FAIL client setup: ' + agent.sanitized_failure(exc, 'client_setup')['explanation'])
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
