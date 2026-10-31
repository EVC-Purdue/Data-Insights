"""Synthetic fixtures and mocked Gemini replies; these are NOT real AI checks."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
import app
from diagnostics import Diagnostics
from simulator import EpisodeCache, SimulatorError, episode_rows, identifier, map_episode, get_json, import_episode


def fixture():
    """Deliberately synthetic, modeled on the inspected public viewer response shape."""
    job = {'id': 'fixture-job', 'status': 'done', 'engine_version': 'synthetic-engine', 'tier_version': 1,
           'recipe': {'source': {'ref': 'fixture', 'commit': 'synthetic'}, 'params': {'example': 1}}}
    episode = {'key': 'fixture-episode', 'outcome': {'handoff_t': 5, 'status': 'failed', 'cause': 'spin'},
        'log': {'t': [-0.05, 0, 0.05, 0.1, 0.15], 'speed': [1, 2, None, 4, 5],
                'wheel': [0, 3, 4, 5, 6], 'ay_mps2': [9, 4, 5, None, 1],
                'x': [0, 1, None, 3, 4], 'y': [0, 1, 2, 3, 4],
                'phase': [1, 2, 2, 2, 2], 'loc_err': [None, 0.1, 0.2, 0.3, 0.4],
                'yaw_rate': [0, 10, 20, 30, 40], 'cmd_speed': [2, 2, 2, 2, 2]},
        'events': [{'t': 0, 'kind': 'handoff'}, {'t': 0.15, 'kind': 'spin'}],
        'lat_limit': {'envelope': 3, 'grip': 4}, 'unsafe': {}, 'metrics': {'cte_p90': None}}
    row = {'key': 'fixture-episode', 'status': 'failed', 'cause': 'spin'}
    return job, episode, row


def run_fixture():
    return map_episode(*fixture(), 'https://simulator.example')


def report_payload(ids=None):
    return {'summary': 'Synthetic mocked report, not a real AI result.',
            'observed_issues': ([{'finding': 'Speed window', 'classification': 'observation', 'evidence_ids': ids}] if ids else []),
            'possible_causes': [], 'uncertainty': ['Synthetic test data'], 'recommended_next_checks': ['Inspect source'],
            'status': 'analysis' if ids else 'insufficient_data'}


class ImportTests(unittest.TestCase):
    def test_units_and_semantics(self):
        run = run_fixture()
        m = run['diagnostic']['measurements']
        self.assertEqual(m['wheel']['unit'], 'deg')
        self.assertEqual(m['yaw_rate']['unit'], 'deg/s')
        self.assertEqual(m['ay_mps2']['unit'], 'm/s^2')
        self.assertEqual(m['loc_err']['kind'], 'estimate_error_against_simulation_truth')
        self.assertEqual(run['telemetry']['steering'], [])
        self.assertEqual(run['telemetry']['acceleration'], [])
        self.assertEqual(run['telemetry']['gps'], [])
        self.assertEqual(run['telemetry']['steeringAngle'][1]['value'], 3)
        self.assertEqual(run['telemetry']['commanded'][2], {'time': 0.05, 'target': 2, 'actual': None})
        self.assertEqual(run['diagnostic']['metrics']['cte_p90']['unit'], 'm')

    def test_null_and_negative_time_preserved(self):
        run = run_fixture()
        self.assertIsNone(run['telemetry']['speed'][2]['value'])
        self.assertEqual(run['telemetry']['speed'][0]['time'], -0.05)
        self.assertEqual(run['diagnostic']['metadata']['time']['handoffSimulatorTime'], 5)
        self.assertIsNone(app.summarize(run)['distance'])

    def test_missing_handoff_not_inferred(self):
        job, episode, row = fixture()
        episode['outcome'] = {}
        run = map_episode(job, episode, row, 'https://simulator.example')
        self.assertEqual(run['diagnostic']['metadata']['time']['basis'], 'simulator_time_handoff_unknown')
        self.assertIsNone(run['diagnostic']['metadata']['time']['handoffSimulatorTime'])

    def test_zero_handoff_is_known(self):
        job, episode, row = fixture()
        episode['outcome']['handoff_t'] = 0
        self.assertEqual(map_episode(job, episode, row, 'https://simulator.example')['diagnostic']['metadata']['time']['basis'], 'handoff_relative')

    def test_bad_mapping_rejected(self):
        for field, value in [('t', [0, 0]), ('speed', [1]), ('speed', [True] * 5), ('t', [float('nan')])]:
            with self.subTest(field=field, value=value):
                job, ep, row = fixture()
                ep['log'][field] = value
                with self.assertRaises(SimulatorError):
                    map_episode(job, ep, row, 'https://simulator.example')

    def test_absent_log_is_usable_metadata_only(self):
        job, ep, row = fixture()
        ep['log'] = {}
        run = map_episode(job, ep, row, 'https://simulator.example')
        self.assertEqual(run['duration'], 0)
        self.assertEqual(Diagnostics(run).signals(), [])

    def test_cache_roundtrip_offline_and_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = EpisodeCache(directory)
            run = run_fixture()
            cache.save(run, fixture()[1])
            Path(directory, 'sim-corrupt.json').write_text('not json')
            loaded, errors = cache.load()
            self.assertEqual(loaded, [run])
            self.assertEqual(len(errors), 1)
            saved = json.loads(Path(directory, run['id'] + '.json').read_text())
            self.assertEqual(saved['originalEpisode'], fixture()[1])

    def test_job_breakdown_laps_and_clips(self):
        rows = episode_rows({'breakdown': {'laps': {'nominal': {'kart1': {'line1': {'key': 'lap-1', 'status': 'ok'}}}},
                                           'clips': {'spin': {'kart2': {'episodes': [{'key': 'clip-1'}]}}}}})
        self.assertEqual({r['key'] for r in rows}, {'lap-1', 'clip-1'})

    def test_path_and_url_injection(self):
        for value in ('../secret', 'http://evil', 'a/b', '', None, 'x?query', 'x\\y'):
            with self.assertRaises(SimulatorError):
                identifier(value)

    def test_real_http_adapter_failures_mocked(self):
        import httpx
        for reply in (httpx.Response(503), httpx.Response(200, text='not JSON'), httpx.Response(302, headers={'location': 'https://evil.example'})):
            transport = httpx.MockTransport(lambda request: reply)
            client = httpx.Client(transport=transport)
            with patch('simulator.httpx.Client', return_value=client):
                with self.assertRaises(SimulatorError):
                    get_json('/api/jobs')
        with patch('simulator.httpx.Client', side_effect=httpx.ConnectTimeout('test-only')):
            with self.assertRaisesRegex(SimulatorError, 'timed out'):
                get_json('/api/jobs')

    def test_import_rejects_running_and_other_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            for detail in ({'job': {'status': 'running'}}, {'job': {'status': 'done'}, 'breakdown': {}}):
                with patch('simulator.job_detail', return_value=detail), patch('simulator.get_json') as fetch:
                    with self.assertRaises(SimulatorError):
                        import_episode('fixture-job', 'fixture-episode', EpisodeCache(directory))
                    fetch.assert_not_called()


class DiagnosticTests(unittest.TestCase):
    def coverage_run(self, samples):
        run = app.new_run('coverage-test', 'Synthetic coverage', 'recording')
        run['duration'] = 10
        run['telemetry']['acceleration'] = samples
        return run

    def test_partial_coverage_uses_run_bounds_even_with_zero_nulls(self):
        diag = Diagnostics(self.coverage_run([{'time': t, 'value': 1} for t in (2, 3, 4, 5)]))
        coverage = diag.coverage('acceleration')
        self.assertEqual(coverage['firstTimestamp'], 2)
        self.assertEqual(coverage['lastTimestamp'], 5)
        self.assertEqual(coverage['nullValues'], 0)
        self.assertEqual(coverage['leadingUncovered'], {'start': 0, 'end': 2, 'duration': 2})
        self.assertEqual(coverage['trailingUncovered'], {'start': 5, 'end': 10, 'duration': 5})
        self.assertEqual(coverage['internalGapCount'], 0)
        self.assertIn(coverage['id'], diag.evidence)
        self.assertEqual(diag.dispatch('signal_coverage', {'signal': 'acceleration'}), coverage)
        self.assertIn(coverage, diag.dispatch('run_overview', {})['coverage'])
        accepted = agent.validate_report(json.dumps(report_payload([coverage['id']])), diag, {coverage['id']})
        self.assertEqual(accepted['evidence'][0]['type'], 'signal_coverage')
        with self.assertRaises(agent.AnalysisError):
            agent.validate_report(json.dumps(report_payload([coverage['id']])), diag, set())

    def test_coverage_distinguishes_internal_gaps_and_null_values(self):
        samples = [{'time': t, 'value': None if t == 2 else 1} for t in (0, 1, 2, 3, 8, 9, 10)]
        coverage = Diagnostics(self.coverage_run(samples)).coverage('acceleration')
        self.assertEqual(coverage['cadenceSeconds'], 1)
        self.assertEqual(coverage['gapThresholdSeconds'], 3)
        self.assertEqual(coverage['internalGaps'], [{'start': 3, 'end': 8, 'duration': 5}])
        self.assertEqual(coverage['internalGapSeconds'], 5)
        self.assertEqual(coverage['nullValues'], 1)
        self.assertEqual(coverage['samples'], 7)
        self.assertIsNone(coverage['leadingUncovered'])
        self.assertIsNone(coverage['trailingUncovered'])
        # A threshold-sized interval is not flagged; insufficient cadence is unknown.
        exact = Diagnostics(self.coverage_run([{'time': t, 'value': 1} for t in (0, 1, 2, 3, 6)]))
        self.assertEqual(exact.coverage('acceleration')['internalGapCount'], 0)
        short = Diagnostics(self.coverage_run([{'time': 0, 'value': 1}, {'time': 8, 'value': 1}]))
        self.assertIsNone(short.coverage('acceleration')['cadenceSeconds'])

    def test_empty_and_all_null_signals_have_distinct_coverage(self):
        empty = Diagnostics(self.coverage_run([])).coverage('acceleration')
        self.assertEqual(empty['state'], 'empty')
        self.assertEqual(empty['samples'], 0)
        self.assertEqual(empty['nullValues'], 0)
        self.assertIsNone(empty['firstTimestamp'])
        self.assertEqual(empty['entireRunUncovered'], {'start': 0, 'end': 10, 'duration': 10})
        nulls = Diagnostics(self.coverage_run([{'time': t, 'value': None} for t in (0, 1, 2, 3)] )).coverage('acceleration')
        self.assertEqual(nulls['state'], 'no_finite_values')
        self.assertEqual(nulls['nullValues'], 4)
        self.assertEqual(nulls['lastTimestamp'], 3)
        self.assertIsNone(nulls['lastFiniteTimestamp'])
        self.assertIsNone(nulls['entireRunUncovered'])

    def test_forward_reverse_signed_mean_does_not_hide_speed_magnitude(self):
        run = self.coverage_run([])
        run['telemetry']['speed'] = [{'time': t, 'value': v} for t, v in enumerate([2, -2, 2, -2])]
        summary = Diagnostics(run).summary('speed')
        self.assertEqual(summary['mean'], 0)
        self.assertEqual(summary['meanAbsolute'], 2)
        self.assertEqual(summary['rms'], 2)
        self.assertEqual(summary['positiveCount'], 2)
        self.assertEqual(summary['negativeCount'], 2)
        self.assertEqual(summary['zeroCount'], 0)

    def test_numeric_summary(self):
        result = Diagnostics(run_fixture()).summary('speed', 0, 0.1)
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['missing'], 1)
        self.assertEqual(result['mean'], 3)
        self.assertEqual(result['max'], {'time': 0.1, 'value': 4})
        self.assertEqual(result['unit'], 'm/s')
        self.assertIn('#log.speed', result['source'])

    def test_empty_window(self):
        result = Diagnostics(run_fixture()).summary('speed', 100, 101)
        self.assertEqual(result['count'], 0)
        self.assertIsNone(result['mean'])

    def test_event_detection_excludes_context_and_preserves_gaps(self):
        events = Diagnostics(run_fixture()).events()['events']
        observed = [e for e in events if e['type'] == 'observed_threshold_exceedance']
        self.assertEqual(len(observed), 1)
        self.assertEqual((observed[0]['start'], observed[0]['end']), (0, 0.05))
        self.assertEqual(observed[0]['threshold']['value'], 3)
        self.assertIn('lat_limit', observed[0]['threshold']['provenance'])
        self.assertTrue(any(e['type'] == 'simulator_label' and e['label'] == 'spin' for e in events))

    def test_no_assumed_threshold(self):
        run = run_fixture()
        run['diagnostic']['latLimit'] = None
        self.assertFalse(any(e['type'] == 'observed_threshold_exceedance' for e in Diagnostics(run).events()['events']))

    def test_legacy_has_no_localization_error(self):
        run = app.new_run('recording', 'Recording', 'recording')
        diag = Diagnostics(run)
        self.assertFalse(any(s['name'] == 'loc_err' for s in diag.signals()))
        self.assertIn('No reference truth', diag.metadata()['limitations'][0])

    def test_invalid_tool_arguments(self):
        diag = Diagnostics(run_fixture())
        invalid = [('shell', {}), ('run_metadata', {'run_id': 'another-run'}),
                   ('available_signals', []), ('time_window_summary', {}),
                   ('time_window_summary', {'signal': 'speed', 'start': True, 'end': None}),
                   ('time_window_summary', {'signal': 'speed', 'start': float('inf'), 'end': None}),
                   ('time_window_summary', {'signal': 'speed', 'start': 2, 'end': 1}),
                   ('time_window_summary', {'signal': 'unknown', 'start': None, 'end': None})]
        for name, args in invalid:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                diag.dispatch(name, args)


class FakeGeminiResponse:
    def __init__(self, parts=(), text=None):
        self.candidates = [SimpleNamespace(content=agent.types.Content(role='model', parts=list(parts)))]
        self.text = text


def gemini_tool_call(name, args):
    return agent.types.Part(function_call=agent.types.FunctionCall(name=name, args=args))


class AgentTests(unittest.TestCase):
    def test_final_context_includes_computed_coverage_even_without_overview_call(self):
        run = app.new_run('coverage', 'coverage', 'recording')
        run['duration'] = 100
        run['telemetry']['acceleration'] = [{'time': t, 'value': 1} for t in range(61)]
        diagnostic = Diagnostics(run)
        model = SimpleNamespace(generate_content=AsyncMock(return_value=FakeGeminiResponse(text=json.dumps(report_payload()))))
        history = []
        asyncio.run(agent.finalize_report(run, SimpleNamespace(models=model), 'mock', diagnostic, history, set(), 6))
        prompt = history[-1]['parts'][0]['text']
        self.assertIn('trailingUncovered', prompt)
        self.assertIn('"duration": 40', prompt)
        self.assertIn('Imported signal availability only', prompt)
        self.assertIn('relationship is unassessed', prompt)
        self.assertEqual(model.generate_content.call_count, 1)
        self.assertIsNone(model.generate_content.call_args.kwargs['config'].tools)

    def test_cross_signal_hypotheses_require_same_focused_windows(self):
        run = app.new_run('aligned', 'aligned', 'recording')
        run['duration'] = 10
        for name in ('speed', 'throttle'):
            run['telemetry'][name] = [{'time': t, 'value': t} for t in range(11)]
        diagnostic = Diagnostics(run)
        for first, second, accepted in [((None, None), (None, None), False), ((2, 4), (5, 7), False), ((2, 4), (2, 4), True)]:
            ids = [diagnostic.summary('speed', *first)['id'], diagnostic.summary('throttle', *second)['id']]
            payload = report_payload()
            payload['possible_causes'] = [{'hypothesis': 'Synthetic cross-signal hypothesis', 'uncertainty': 'Not proven', 'evidence_ids': ids}]
            if accepted:
                agent.validate_report(json.dumps(payload), diagnostic, set(ids))
            else:
                with self.assertRaisesRegex(agent.AnalysisError, 'aligned focused-window'):
                    agent.validate_report(json.dumps(payload), diagnostic, set(ids))

    def test_bounded_tool_trace_and_structural_evidence_delivery(self):
        run = run_fixture()
        diagnostic = Diagnostics(run)
        ev = diagnostic.summary('speed')
        self.assertEqual(agent.delivered_ids({'text': ev['id']}, diagnostic), set())
        self.assertEqual(agent.delivered_ids({'evidence': [ev]}, diagnostic), {ev['id']})
        batch = FakeGeminiResponse([gemini_tool_call('run_overview' if i == 0 else 'run_metadata', {}) for i in range(8)])
        batch.candidates[0].content.parts[0].thought_signature = b'SECRET_SIGNATURE'
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[batch, FakeGeminiResponse(text=json.dumps(report_payload()))]))
        with patch.dict('os.environ', {'GEMINI_DIAGNOSTIC_TRACE': '1'}), self.assertLogs(agent.logger) as logs:
            result = asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
        trace = json.loads(next(line.split('Gemini tool trace: ')[1] for line in logs.output if 'Gemini tool trace:' in line))
        self.assertEqual((trace['requested'], trace['attempted'], trace['executedSuccessfully']), (8, 6, 6))
        self.assertEqual(result['toolCalls'], 6)
        self.assertEqual(trace['entries'][6]['outcome'], 'budget_rejected')
        self.assertFalse(trace['entries'][6]['executedSuccessfully'])
        self.assertTrue(trace['entries'][0]['deliveredEvidenceIds'])
        self.assertNotIn('SECRET_SIGNATURE', ''.join(logs.output))

    def test_output_limited_overview_delivers_no_tool_evidence(self):
        run = run_fixture()
        run['diagnostic']['metadata']['limitations'] = ['x' * 17000]
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse([gemini_tool_call('run_overview', {})]),
            FakeGeminiResponse([agent.types.Part(text='done')]),
            FakeGeminiResponse(text=json.dumps(report_payload()))]))
        with patch.dict('os.environ', {'GEMINI_DIAGNOSTIC_TRACE': '1'}), self.assertLogs(agent.logger) as logs:
            asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
        trace = json.loads(next(line.split('Gemini tool trace: ')[1] for line in logs.output if 'Gemini tool trace:' in line))
        self.assertEqual(trace['entries'][0]['outcome'], 'output_limit')
        self.assertEqual(trace['entries'][0]['deliveredEvidenceIds'], [])

    def test_provider_report_schema_keeps_frontend_structure_without_constraints(self):
        schema = agent.provider_report_schema()
        expected = {'summary', 'observed_issues', 'possible_causes', 'uncertainty', 'recommended_next_checks', 'status'}
        self.assertEqual(schema['type'], 'object')
        self.assertEqual(set(schema['properties']), expected)
        self.assertEqual(set(schema['required']), expected)
        self.assertEqual(schema['properties']['summary'], {'type': 'string'})
        self.assertEqual(schema['properties']['status']['enum'], ['analysis', 'insufficient_data'])
        for field, names in [('observed_issues', {'finding', 'classification', 'evidence_ids'}),
                             ('possible_causes', {'hypothesis', 'evidence_ids', 'uncertainty'})]:
            array = schema['properties'][field]
            self.assertEqual(array['type'], 'array')
            item = array['items']
            self.assertEqual(item['type'], 'object')
            self.assertEqual(set(item['properties']), names)
            self.assertEqual(set(item['required']), names)
            self.assertEqual(item['properties']['evidence_ids'], {'type': 'array', 'items': {'type': 'string'}})
        self.assertEqual(schema['properties']['observed_issues']['items']['properties']['classification']['enum'],
                         ['observation', 'simulator_label'])
        for field in ('uncertainty', 'recommended_next_checks'):
            self.assertEqual(schema['properties'][field], {'type': 'array', 'items': {'type': 'string'}})
        wire = json.dumps(schema)
        for keyword in ('minLength', 'maxLength', 'minItems', 'maxItems', 'additionalProperties', '$ref', '$defs', 'title'):
            self.assertNotIn(keyword, wire)

    def test_simple_provider_schema_does_not_relax_local_report_validation(self):
        diag = Diagnostics(run_fixture())
        ev = diag.summary('speed')['id']
        valid = report_payload([ev])
        for field, value in [('summary', ''), ('summary', 'x' * 2001), ('summary', 42),
                             ('uncertainty', []), ('uncertainty', ['x'] * 13),
                             ('recommended_next_checks', ['x'] * 13), ('status', 'unsupported'),
                             ('observed_issues', valid['observed_issues'] * 13)]:
            payload = deepcopy(valid)
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(agent.ValidationError):
                agent.validate_report(json.dumps(payload), diag, {ev})
        for patch_finding in ({'evidence_ids': []}, {'evidence_ids': [ev] * 9},
                              {'finding': 'x' * 1201}, {'classification': 'guess'}, {'extra': 'not allowed'}):
            payload = deepcopy(valid)
            payload['observed_issues'][0].update(patch_finding)
            with self.assertRaises(agent.ValidationError):
                agent.validate_report(json.dumps(payload), diag, {ev})
        for payload in ({**valid, 'extra': 'not allowed'}, {k: v for k, v in valid.items() if k != 'status'}):
            with self.assertRaises(agent.ValidationError):
                agent.validate_report(json.dumps(payload), diag, {ev})
        for evidence, delivered in [('fabricated', {ev}), (ev, set()), (diag.summary('speed', 100, 101)['id'], None)]:
            with self.assertRaises(agent.AnalysisError):
                agent.validate_report(json.dumps(report_payload([evidence])), diag, delivered)
        label = next(e for e in diag.events()['events'] if e['type'] == 'simulator_label')
        with self.assertRaisesRegex(agent.AnalysisError, 'misclassified'):
            agent.validate_report(json.dumps(report_payload([label['id']])), diag)
        self.assertEqual(agent.validate_report(json.dumps(valid), diag, {ev})['evidence'][0]['id'], ev)

    def test_schema_reductions_are_bounded_and_stop_on_non_schema_errors(self):
        import diagnose_gemini
        import io
        from contextlib import redirect_stdout
        invalid = agent.errors.APIError(400, {'error': {'status': 'INVALID_ARGUMENT', 'message': 'max_items schema'}})
        quota = agent.errors.APIError(429, {'error': {'status': 'RESOURCE_EXHAUSTED'}})
        for responses, expected, count in [([invalid] * 4, False, 4), ([quota], False, 1),
                ([invalid, FakeGeminiResponse(text=json.dumps(report_payload()))], True, 2)]:
            model = SimpleNamespace(generate_content=AsyncMock(side_effect=responses))
            with redirect_stdout(io.StringIO()):
                result = asyncio.run(diagnose_gemini.reduce_schema(SimpleNamespace(models=model), 'mock', 1))
            self.assertEqual(result, expected)
            self.assertEqual(model.generate_content.call_count, count)

    def test_tool_json_schema_uses_nullable_json_types(self):
        schema = next(t.parameters_json_schema for t in agent.tools() if t.name == 'time_window_summary')
        for name in ('start', 'end'):
            self.assertEqual(schema['properties'][name]['type'], ['number', 'null'])
            self.assertNotIn('nullable', schema['properties'][name])
        self.assertEqual(set(schema['required']), {'signal', 'start', 'end'})

    def test_provider_diagnostic_is_backend_only_and_allowlisted(self):
        secret = 'SECRET_KEY_RAW_TELEMETRY_SIGNATURE'
        error = agent.errors.APIError(400, {'error': {'status': 'INVALID_ARGUMENT',
            'message': 'Schema produces too many states: ' + secret,
            'details': [{'reason': secret}]}})
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=error))
        with self.assertLogs(agent.logger, level='WARNING') as logs, self.assertRaises(agent.AnalysisError) as caught:
            asyncio.run(agent.generate_content(SimpleNamespace(models=model), phase='structured_finalization'))
        output = '\n'.join(logs.output)
        self.assertIn('structured_finalization', output)
        self.assertIn('"http_status": 400', output)
        self.assertIn('"provider_code": 400', output)
        self.assertIn('INVALID_ARGUMENT', output)
        self.assertIn('complexity', output)
        self.assertNotIn(secret, output + str(caught.exception))
        self.assertNotIn('complexity', str(caught.exception))
        self.assertEqual(caught.exception.category, 'gemini_request_error')
        error.status = secret
        self.assertEqual(agent.sanitized_failure(error, secret)['provider_status'], 'UNKNOWN')
        self.assertEqual(agent.sanitized_failure(error, secret)['phase'], 'unknown')
        error.message = "Unknown max_items at response_schema.properties.observed_issues.items.properties.evidence_ids: " + secret
        detail = agent.sanitized_failure(error, 'report_schema')
        self.assertIn('maxItems', detail['schema_keywords'])
        self.assertIn('responseSchema', detail['schema_keywords'])
        self.assertEqual(detail['schema_fields'], ['evidence_ids', 'observed_issues'])
        self.assertNotIn(secret, json.dumps(detail))

    def test_sdk_serializes_tool_schema_without_live_network(self):
        import httpx
        captured = []
        async def transport(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': 'OK'}]}}]})
        async def check():
            options = agent.types.HttpOptions(async_client_args={'transport': httpx.MockTransport(transport)},
                retry_options=agent.types.HttpRetryOptions(attempts=1))
            async with agent.genai.Client(vertexai=False, api_key='synthetic-test-only', http_options=options).aio as client:
                await client.models.generate_content(model='gemini-test', contents='Synthetic',
                    config=agent.types.GenerateContentConfig(tools=[agent.types.Tool(function_declarations=agent.tools())],
                        automatic_function_calling=agent.types.AutomaticFunctionCallingConfig(disable=True)))
                await client.models.generate_content(model='gemini-test', contents='Synthetic',
                    config=agent.types.GenerateContentConfig(response_mime_type='application/json',
                        response_json_schema=agent.provider_report_schema()))
        asyncio.run(check())
        declaration = next(t for t in captured[0]['tools'][0]['functionDeclarations'] if t['name'] == 'time_window_summary')
        self.assertEqual(declaration['parameters_json_schema']['properties']['start'], {'type': ['number', 'null']})
        self.assertEqual(captured[1]['generationConfig']['responseJsonSchema'], agent.provider_report_schema())
        self.assertNotIn('responseSchema', captured[1]['generationConfig'])

    def test_live_probe_is_opt_in_and_stops_at_first_mocked_failure(self):
        import diagnose_gemini
        import io
        from contextlib import redirect_stdout
        with patch.object(sys, 'argv', ['diagnose_gemini.py']), patch.object(diagnose_gemini, 'probe') as probe:
            with redirect_stdout(io.StringIO()), patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit):
                diagnose_gemini.main()
            probe.assert_not_called()
        output = io.StringIO()
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse(text='OK'), agent.errors.APIError(400, {'error': {
                'status': 'INVALID_ARGUMENT', 'message': 'schema unsupported SECRET'}})]))
        args = SimpleNamespace(run_id='real-run-must-not-be-called', endpoint='http://127.0.0.1:5000')
        with patch.object(agent, '_configuration', return_value=('synthetic-test-only', 'gemini-test', 10, 30)), \
             patch.object(agent.genai, 'Client') as sdk, patch('diagnose_gemini.httpx.AsyncClient') as endpoint:
            sdk.return_value.aio.__aenter__ = AsyncMock(return_value=SimpleNamespace(models=model))
            sdk.return_value.aio.__aexit__ = AsyncMock(return_value=False)
            with redirect_stdout(output), self.assertLogs(agent.logger) as logs:
                result = asyncio.run(diagnose_gemini.probe(args))
        self.assertEqual(result, 1)
        self.assertEqual(model.generate_content.call_count, 2)
        endpoint.assert_not_called()
        self.assertIn('PASS a', output.getvalue())
        self.assertIn('FAIL b', output.getvalue())
        self.assertNotIn('PASS c', output.getvalue())
        self.assertNotIn('SECRET', output.getvalue() + ''.join(logs.output))
        self.assertEqual(sdk.call_args.kwargs['http_options'].retry_options.attempts, 1)

    def test_binary_fields_survive_multiple_turns_and_final_report(self):
        signature = b'\x00\xff\x80opaque-signature'
        first = FakeGeminiResponse([
            agent.types.Part(function_call=agent.types.FunctionCall(name='run_metadata', args={}, id='call-1'), thought_signature=signature),
            agent.types.Part(inline_data=agent.types.Blob(mime_type='application/octet-stream', data=b'\xfe\x00'))])
        second = FakeGeminiResponse([gemini_tool_call('available_signals', {})])
        done = FakeGeminiResponse([agent.types.Part(text='done', thought_signature=signature)])
        responses = iter([first, second, done, FakeGeminiResponse(text=json.dumps(report_payload()))])
        histories = []

        async def generate(**kwargs):
            histories.append(list(kwargs['contents']))
            return next(responses)

        client = SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(side_effect=generate)))
        result = asyncio.run(agent.investigate(run_fixture(), client, 'mock'))
        self.assertEqual(result['toolCalls'], 2)
        self.assertEqual(len(histories), 4)
        for history in histories[1:]:
            self.assertIs(history[1], first.candidates[0].content)
            self.assertEqual(history[1].parts[0].thought_signature, signature)
            self.assertEqual(history[1].parts[1].inline_data.data, b'\xfe\x00')
            self.assertEqual(history[2].parts[0].function_response.id, 'call-1')
            json.loads(agent._context_json(history))
        self.assertIs(histories[-1][-2], done.candidates[0].content)
        with patch.object(agent, 'MAX_CONTEXT', 100), self.assertRaisesRegex(agent.AnalysisError, 'context limit'):
            # The normal first prompt already exceeds this limit.
            asyncio.run(agent.investigate(run_fixture(), client, 'mock'))

    def test_default_provider_and_configuration(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(agent.selected_provider(), 'gemini')
            self.assertFalse(agent.configured())
            with self.assertRaisesRegex(agent.AnalysisError, 'GEMINI_API_KEY'):
                agent.analyze(run_fixture())
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'local-test-key'}, clear=True):
            self.assertTrue(agent.configured())
            self.assertEqual(agent._configuration()[1], 'gemini-3.5-flash-lite')
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test', 'GEMINI_MODEL': 'gemini-custom'}, clear=True):
            self.assertEqual(agent._configuration()[1], 'gemini-custom')

    def test_no_provider_fallback(self):
        with patch.dict('os.environ', {'AI_PROVIDER': 'ollama', 'GEMINI_API_KEY': 'test', 'OLLAMA_MODEL': 'qwen3:4b'}, clear=True):
            with self.assertRaisesRegex(agent.AnalysisError, 'must be gemini'):
                agent.analyze(run_fixture())

    def test_gemini_tool_loop_and_structured_report(self):
        run = run_fixture()
        ev = Diagnostics(run).summary('speed')['id']
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse([gemini_tool_call('time_window_summary', {'signal': 'speed', 'start': None, 'end': None})]),
            FakeGeminiResponse([agent.types.Part(text='investigation complete')]),
            FakeGeminiResponse(text=json.dumps(report_payload([ev])))]))
        client = SimpleNamespace(models=model)
        result = asyncio.run(agent.investigate(run, client, 'gemini-3.5-flash-lite'))
        self.assertEqual(result['provider'], 'Gemini API')
        self.assertEqual(result['toolCalls'], 1)
        self.assertEqual(result['report']['evidence'][0]['id'], ev)
        calls = model.generate_content.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[0].kwargs['config'].automatic_function_calling.disable)
        self.assertIsNotNone(calls[0].kwargs['config'].tools)
        self.assertIsNotNone(calls[1].kwargs['config'].tools)
        self.assertIsNone(calls[2].kwargs['config'].tools)
        self.assertEqual(calls[2].kwargs['config'].response_mime_type, 'application/json')
        self.assertEqual(calls[2].kwargs['config'].response_json_schema, agent.provider_report_schema())
        self.assertIn('functionResponse', agent._context_json(calls[1].kwargs['contents']))

    def test_invalid_tool_args_do_not_supply_evidence(self):
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse([gemini_tool_call('run_metadata', {'run_id': 'other'})]),
            FakeGeminiResponse([agent.types.Part(text='done')]),
            FakeGeminiResponse(text=json.dumps(report_payload(['fabricated'])))]))
        with self.assertRaisesRegex(agent.AnalysisError, 'failed schema or evidence'):
            asyncio.run(agent.investigate(run_fixture(), SimpleNamespace(models=model), 'mock'))
        history = model.generate_content.call_args_list[2].kwargs['contents']
        self.assertIn('error', history[2].parts[0].function_response.response)
        self.assertNotIn('fabricated', agent._context_json(history))

    def test_tool_limit_and_context_limit(self):
        repeated = [FakeGeminiResponse([gemini_tool_call('run_metadata', {})]) for _ in range(6)]
        repeated += [FakeGeminiResponse(text=json.dumps(report_payload()))]
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=repeated))
        diagnostic = Diagnostics(run_fixture())
        with patch.object(agent, 'Diagnostics', return_value=diagnostic), patch.object(diagnostic, 'dispatch', wraps=diagnostic.dispatch) as dispatch:
            result = asyncio.run(agent.investigate(run_fixture(), SimpleNamespace(models=model), 'mock'))
        self.assertEqual(dispatch.call_count, 6)
        self.assertEqual(result['toolCalls'], 6)
        self.assertEqual(result['report']['status'], 'insufficient_data')
        self.assertEqual(result['report']['evidence'], [])
        self.assertEqual(model.generate_content.call_count, 7)
        config = model.generate_content.call_args_list[6].kwargs['config']
        self.assertIsNone(config.tools)
        self.assertTrue(config.automatic_function_calling.disable)
        self.assertEqual(config.response_json_schema, agent.provider_report_schema())
        run = run_fixture()
        run['diagnostic']['metadata']['notes'] = 'untrusted data ' * 5000
        model = SimpleNamespace(generate_content=AsyncMock())
        with patch.object(agent, 'MAX_CONTEXT', 1), self.assertRaisesRegex(agent.AnalysisError, 'context limit'):
            asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
        model.generate_content.assert_not_called()

    def test_parallel_calls_over_budget_receive_matching_responses_and_finalize(self):
        # Exercise both an oversized initial batch and a batch with one slot left.
        for prior_calls in (0, 5):
            with self.subTest(prior_calls=prior_calls):
                run = run_fixture()
                diagnostic = Diagnostics(run)
                ev = Diagnostics(run).summary('speed')['id']
                replies = [FakeGeminiResponse([gemini_tool_call('run_metadata', {})]) for _ in range(prior_calls)]
                batch = FakeGeminiResponse([
                    agent.types.Part(function_call=agent.types.FunctionCall(
                        name='time_window_summary', id=f'call-{i}',
                        args={'signal': 'speed' if i < 6 - prior_calls else 'wheel', 'start': None, 'end': None}),
                        thought_signature=b'\xff\x00signature' if i == 0 else None)
                    for i in range(8 - prior_calls)])
                replies += [batch, FakeGeminiResponse(text=json.dumps(report_payload([ev])))]
                model = SimpleNamespace(generate_content=AsyncMock(side_effect=replies))
                with patch.object(agent, 'Diagnostics', return_value=diagnostic), patch.object(diagnostic, 'dispatch', wraps=diagnostic.dispatch) as dispatch:
                    result = asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
                self.assertEqual(dispatch.call_count, 6)
                self.assertEqual(result['toolCalls'], 6)
                self.assertEqual(result['report']['evidence'][0]['id'], ev)
                self.assertFalse(any(call.args[1].get('signal') == 'wheel' for call in dispatch.call_args_list))
                self.assertEqual(model.generate_content.call_count, prior_calls + 2)
                final = model.generate_content.call_args_list[-1].kwargs
                self.assertIsNone(final['config'].tools)
                self.assertTrue(final['config'].automatic_function_calling.disable)
                self.assertEqual(final['config'].response_json_schema, agent.provider_report_schema())
                self.assertIs(final['contents'][-3], batch.candidates[0].content)
                self.assertEqual(final['contents'][-3].parts[0].thought_signature, b'\xff\x00signature')
                responses = final['contents'][-2].parts
                self.assertEqual(len(responses), 8 - prior_calls)
                for i, part in enumerate(responses):
                    response = part.function_response
                    self.assertEqual(response.id, f'call-{i}')
                    self.assertEqual(response.name, 'time_window_summary')
                    if i < 6 - prior_calls:
                        self.assertEqual(response.response['id'], ev)
                    else:
                        self.assertEqual(response.response['error']['code'], 'tool_budget_exhausted')
                self.assertEqual({k for k, v in diagnostic.evidence.items() if v['type'] == 'window_summary'}, {ev})

    def test_finalization_never_executes_more_tools_or_retries(self):
        run = run_fixture()
        for final in (FakeGeminiResponse([gemini_tool_call('detected_events', {})], text=json.dumps(report_payload())),
                      FakeGeminiResponse(text=json.dumps(report_payload(['uncollected-evidence'])))):
            diagnostic = Diagnostics(run)
            model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
                FakeGeminiResponse([gemini_tool_call('run_metadata', {}) for _ in range(6)]), final]))
            with patch.object(agent, 'Diagnostics', return_value=diagnostic), patch.object(diagnostic, 'dispatch', wraps=diagnostic.dispatch) as dispatch:
                with self.assertRaises(agent.AnalysisError) as caught:
                    asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
            self.assertEqual(caught.exception.category, 'invalid_report')
            self.assertEqual(dispatch.call_count, 6)
            self.assertEqual(model.generate_content.call_count, 2)

    def test_api_error_categories_and_sanitized_quota(self):
        error = agent.errors.APIError(429, {'error': {'message': 'SECRET_RESPONSE', 'status': 'RESOURCE_EXHAUSTED'}})
        with self.assertLogs(agent.logger, level='WARNING') as logs, self.assertRaises(agent.AnalysisError) as caught:
            agent._gemini_error(error)
        self.assertEqual(caught.exception.category, 'gemini_quota_exhausted')
        self.assertIn('free-tier quota', str(caught.exception))
        self.assertNotIn('SECRET_RESPONSE', str(caught.exception) + ''.join(logs.output))
        self.assertNotIn('GEMINI_API_KEY', ''.join(logs.output))

    def test_timeout_and_api_error_categories(self):
        for code, status, category in [(401, 'UNAUTHENTICATED', 'gemini_authentication'),
                                       (404, 'NOT_FOUND', 'gemini_model_unavailable'),
                                       (503, 'UNAVAILABLE', 'gemini_service_error')]:
            with self.assertRaises(agent.AnalysisError) as caught:
                agent._gemini_error(agent.errors.APIError(code, {'error': {'status': status}}))
            self.assertEqual(caught.exception.category, category)
        async def stalled(*args):
            await asyncio.sleep(1)
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test'}, clear=True), patch.object(agent, '_configuration', return_value=('test', 'mock', 1, 0.01)), patch.object(agent, 'investigate', stalled), patch.object(agent.genai, 'Client') as client:
            client.return_value.aio.__aenter__ = AsyncMock(return_value=SimpleNamespace())
            client.return_value.aio.__aexit__ = AsyncMock(return_value=False)
            with self.assertRaisesRegex(agent.AnalysisError, 'timed out'):
                agent.analyze(run_fixture())

    def test_report_evidence_validation(self):
        diag = Diagnostics(run_fixture())
        with self.assertRaises(agent.AnalysisError):
            agent.validate_report(json.dumps(report_payload(['fabricated'])), diag)
        label = next(e for e in diag.events()['events'] if e['type'] == 'simulator_label')
        with self.assertRaisesRegex(agent.AnalysisError, 'misclassified'):
            agent.validate_report(json.dumps(report_payload([label['id']])), diag)
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.run = run_fixture()
        self.previous = dict(app.runs)
        app.runs.clear()
        app.runs[self.run['id']] = self.run
        self.client = app.app.test_client()

    def tearDown(self):
        app.runs.clear()
        app.runs.update(self.previous)


    def test_gemini_api_categories_are_returned_to_frontend(self):
        for status, code, expected in ((429, 'insufficient_quota', 'quota'),
                                       (429, 'rate_limit_exceeded', 'quota'),
                                       (403, '-', 'account_access'),
                                       (404, '-', 'model_configuration'),
                                       (503, '-', 'provider_service'),
                                       (None, '-', 'connectivity')):
            self.assertEqual(('quota' if status == 429 else 'account_access' if status == 403 else 'model_configuration' if status == 404 else 'provider_service' if status == 503 else 'connectivity'), expected)
        with patch.object(agent, 'configured', return_value=True), \
             patch.object(agent, 'analyze', side_effect=agent.AnalysisError(
                 'Gemini rejected authentication. Check the backend GEMINI_API_KEY.',
                 'gemini_authentication')):
            result = self.client.post(f'/api/runs/{self.run["id"]}/analyze')
        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json['category'], 'gemini_authentication')
        self.assertIn('Check the backend GEMINI_API_KEY', result.json['error'])
        self.assertNotIn('key value', result.get_data(as_text=True))

    def test_existing_contract_and_diagnostics(self):
        self.assertEqual(self.client.get('/api/runs').status_code, 200)
        data = self.client.get(f'/api/runs/{self.run["id"]}/telemetry').json
        self.assertIn('controller', data)
        self.assertIsNone(data['telemetry']['speed'][2]['value'])
        self.assertEqual(self.client.get(f'/api/runs/{self.run["id"]}/diagnostics').status_code, 200)
        self.assertEqual(self.client.get('/api/runs/missing/diagnostics').status_code, 404)

    def test_analysis_endpoint_returns_frontend_report_contract(self):
        ev = Diagnostics(self.run).summary('speed')['id']
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse([gemini_tool_call('time_window_summary', {'signal': 'speed', 'start': None, 'end': None})]),
            FakeGeminiResponse([agent.types.Part(text='done', thought_signature=b'\xff\x00')]),
            FakeGeminiResponse(text=json.dumps(report_payload([ev])))]))
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'}, clear=True), patch.object(agent.genai, 'Client') as sdk:
            sdk.return_value.aio.__aenter__ = AsyncMock(return_value=SimpleNamespace(models=model))
            sdk.return_value.aio.__aexit__ = AsyncMock(return_value=False)
            response = self.client.post(f'/api/runs/{self.run["id"]}/analyze')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['runId'], self.run['id'])
        self.assertEqual(response.json['provider'], 'Gemini API')
        self.assertEqual(response.json['toolCalls'], 1)
        self.assertEqual(response.json['report']['evidence'][0]['id'], ev)
        self.assertIn('basis', response.json['snapshot'])
        self.assertFalse(sdk.call_args.kwargs['vertexai'])

    def test_missing_ai_still_allows_deterministic(self):
        with patch.dict('os.environ', {'AI_PROVIDER': 'gemini'}, clear=True):
            result = self.client.post(f'/api/runs/{self.run["id"]}/analyze')
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json['error'], 'AI analysis not configured')
            self.assertEqual(self.client.get(f'/api/runs/{self.run["id"]}/diagnostics').status_code, 200)

    def test_api_error_and_slot_released(self):
        with patch.dict('os.environ', {'AI_PROVIDER': 'gemini'}, clear=True), patch.object(agent, 'configured', return_value=True), patch.object(agent, 'analyze', side_effect=agent.AnalysisError('AI test failure')):
            for _ in range(2):
                self.assertEqual(self.client.post(f'/api/runs/{self.run["id"]}/analyze').status_code, 502)

    def test_readonly_simulator_failure_and_validation(self):
        with patch.object(app, 'jobs', side_effect=SimulatorError('Simulator request timed out')):
            self.assertEqual(self.client.get('/api/simulator/jobs').status_code, 502)
        self.assertEqual(self.client.post('/api/simulator/import', json={'url': 'https://evil'}).status_code, 400)
        self.assertEqual(self.client.delete('/api/simulator/jobs/job').status_code, 404)

    def test_cors_and_origin(self):
        url = f'/api/runs/{self.run["id"]}/analyze'
        self.assertEqual(self.client.post(url, headers={'Origin': 'https://evil.example'}).status_code, 403)
        result = self.client.options(url, headers={'Origin': 'http://localhost:5173'})
        self.assertIn('POST', result.headers['Access-Control-Allow-Methods'])

    def test_live_snapshot_preserves_existing_contract(self):
        live = app.new_run('live', 'Jetson', 'live')
        live['telemetry']['speed'] = [{'time': 10, 'value': 2}, {'time': 11, 'value': 3}]
        app.runs['live'] = live
        diag = self.client.get('/api/runs/live/diagnostics').json
        self.assertEqual(diag['metadata']['time']['basis'], 'laptop_arrival_relative')
        self.assertEqual(diag['signals'][0]['kind'], 'estimate')
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertEqual(self.client.get('/api/runs/live/telemetry').json['distance'], 2.5)

    def test_busy_analysis_returns_429(self):
        with patch.dict('os.environ', {'AI_PROVIDER': 'gemini'}, clear=True), patch.object(agent, 'configured', return_value=True):
            app.analysis_slot.acquire()
            try:
                self.assertEqual(self.client.post(f'/api/runs/{self.run["id"]}/analyze').status_code, 429)
            finally:
                app.analysis_slot.release()


if __name__ == '__main__':
    unittest.main()
