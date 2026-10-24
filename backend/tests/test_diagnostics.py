"""Synthetic fixtures and mocked Responses API replies; these are NOT real AI checks."""
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


class FakeCall:
    type = 'function_call'
    def __init__(self, name, arguments='{}'):
        self.name, self.arguments, self.call_id = name, arguments, 'synthetic-call'
    def model_dump(self, **kwargs):
        return {'type': self.type, 'name': self.name, 'arguments': self.arguments, 'call_id': self.call_id}


def response(calls=(), report=None, status='completed'):
    return SimpleNamespace(status=status, output=list(calls), output_text=json.dumps(report or report_payload()))


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


class AgentTests(unittest.TestCase):
    def test_mocked_tool_loop_with_evidence(self):
        run = run_fixture()
        ev = Diagnostics(run).summary('speed')['id']
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[
            response([FakeCall('time_window_summary', '{"signal":"speed","start":null,"end":null}')]),
            response(report=report_payload([ev]))])))
        result = asyncio.run(agent.investigate(run, client, 'mock-model'))
        self.assertEqual(result['toolCalls'], 1)
        self.assertEqual(result['report']['evidence'][0]['mean'], 3)
        self.assertFalse(client.responses.create.call_args.kwargs['store'])

    def test_tool_budget(self):
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response([FakeCall('run_metadata')]))))
        with self.assertRaisesRegex(agent.AnalysisError, 'tool-call limit'):
            asyncio.run(agent.investigate(run_fixture(), client, 'mock-model'))
        self.assertEqual(client.responses.create.call_count, 7)

    def test_invalid_tool_recoverable(self):
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[
            response([FakeCall('run_metadata', '{"run_id":"other"}')]), response()])))
        result = asyncio.run(agent.investigate(run_fixture(), client, 'mock-model'))
        self.assertEqual(result['report']['status'], 'insufficient_data')
        self.assertIn('Invalid tool arguments', client.responses.create.call_args.kwargs['input'][-1]['output'])

    def test_unsupported_and_misclassified_evidence(self):
        diag = Diagnostics(run_fixture())
        with self.assertRaises(agent.AnalysisError):
            agent.validate_report(json.dumps(report_payload(['fabricated'])), diag)
        label = next(e for e in diag.events()['events'] if e['type'] == 'simulator_label')
        with self.assertRaisesRegex(agent.AnalysisError, 'misclassified'):
            agent.validate_report(json.dumps(report_payload([label['id']])), diag)

    def test_invalid_report_and_empty_evidence(self):
        diag = Diagnostics(run_fixture())
        ev = diag.summary('speed', 200, 300)
        with self.assertRaises(agent.AnalysisError):
            agent.validate_report(json.dumps(report_payload([ev['id']])), diag)
        with self.assertRaises(ValueError):
            agent.validate_report('{}', diag)

    def test_no_tools_and_incomplete_response(self):
        for value in (response(), response(status='incomplete')):
            client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=value)))
            with self.assertRaises(agent.AnalysisError):
                asyncio.run(agent.investigate(run_fixture(), client, 'mock-model'))

    def test_context_limit(self):
        run = run_fixture()
        run['diagnostic']['metadata']['job']['notes'] = 'untrusted data ' * 2000
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=[response([FakeCall('run_metadata')]), response()])))
        asyncio.run(agent.investigate(run, client, 'mock-model'))
        self.assertIn('Result exceeds', client.responses.create.call_args.kwargs['input'][-1]['output'])

    def test_missing_credentials(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(agent.AnalysisError, 'not configured'):
            agent.analyze(run_fixture())

    def test_api_failure_and_timeout_sanitized(self):
        import httpx
        from openai import APIConnectionError
        for error in [APIConnectionError(request=httpx.Request('POST', 'https://api.openai.com/v1/responses')),
                      asyncio.TimeoutError()]:
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only', 'OPENAI_MODEL': 'mock-model'}), \
                 patch.object(agent, 'investigate', AsyncMock(side_effect=error)), \
                 self.assertRaises(agent.AnalysisError) as context:
                agent.analyze(run_fixture())
            self.assertNotIn('test-only', str(context.exception))

    def test_total_deadline_cancels_investigation(self):
        async def stalled(*args):
            await asyncio.sleep(1)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only', 'OPENAI_MODEL': 'mock-model'}), \
             patch.object(agent, 'MAX_SECONDS', 0.01), patch.object(agent, 'investigate', stalled):
            with self.assertRaisesRegex(agent.AnalysisError, 'timed out'):
                agent.analyze(run_fixture())

    def test_oversized_context_rejected_before_api(self):
        client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
        with patch.object(agent, 'MAX_CONTEXT', 1), self.assertRaisesRegex(agent.AnalysisError, 'context limit'):
            asyncio.run(agent.investigate(run_fixture(), client, 'mock-model'))
        client.responses.create.assert_not_called()


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

    def test_existing_contract_and_diagnostics(self):
        self.assertEqual(self.client.get('/api/runs').status_code, 200)
        data = self.client.get(f'/api/runs/{self.run["id"]}/telemetry').json
        self.assertIn('controller', data)
        self.assertIsNone(data['telemetry']['speed'][2]['value'])
        self.assertEqual(self.client.get(f'/api/runs/{self.run["id"]}/diagnostics').status_code, 200)
        self.assertEqual(self.client.get('/api/runs/missing/diagnostics').status_code, 404)

    def test_missing_ai_still_allows_deterministic(self):
        with patch.dict('os.environ', {}, clear=True):
            result = self.client.post(f'/api/runs/{self.run["id"]}/analyze')
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json['error'], 'AI analysis not configured')
            self.assertEqual(self.client.get(f'/api/runs/{self.run["id"]}/diagnostics').status_code, 200)

    def test_api_error_and_slot_released(self):
        with patch.object(agent, 'configured', return_value=True), patch.object(agent, 'analyze', side_effect=agent.AnalysisError('AI test failure')):
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
        with patch.object(agent, 'configured', return_value=True):
            app.analysis_slot.acquire()
            try:
                self.assertEqual(self.client.post(f'/api/runs/{self.run["id"]}/analyze').status_code, 429)
            finally:
                app.analysis_slot.release()


if __name__ == '__main__':
    unittest.main()
