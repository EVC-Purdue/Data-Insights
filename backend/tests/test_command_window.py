"""Offline command comparison and mocked Gemini protocol checks."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import agent
from diagnostics import Diagnostics, WindowTooLarge
from test_diagnostics import FakeGeminiResponse, gemini_tool_call, report_payload


def run_with(command_times=range(11), speed_times=range(11)):
    run = app.new_run('synthetic', 'synthetic', 'recording')
    run['duration'] = 20
    for name, times in (('commanded', command_times), ('speed', speed_times)):
        run['telemetry'][name] = [{'time': t, 'value': float(t % 3)} for t in times]
    return run


class CommandWindowTests(unittest.TestCase):
    def test_oversized_error_suggestion_and_retry(self):
        run = run_with(range(100), range(100))
        run['duration'] = 100
        d = Diagnostics(run)
        with self.assertRaises(WindowTooLarge) as caught:
            d.command_speed_window(0, 84)
        payload = caught.exception.payload
        self.assertEqual(payload['error']['code'], 'window_too_large')
        self.assertEqual(payload['error']['requestedDurationSeconds'], 84)
        self.assertEqual(payload['error']['maximumDurationSeconds'], 30)
        self.assertEqual(d.evidence, {})
        self.assertLess(len(json.dumps(payload)), 1000)
        suggestion = payload['error']['suggestedWindow']
        self.assertEqual(suggestion, {'start': 0, 'end': 30})
        ids = [x['id'] for x in d.command_speed_window(**suggestion)['summaries']]
        first = FakeGeminiResponse([gemini_tool_call('command_speed_window', {'start': 0, 'end': 84})])
        first.candidates[0].content.parts[0].thought_signature = b'opaque-signature'
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[first,
            FakeGeminiResponse([gemini_tool_call('command_speed_window', suggestion)]),
            FakeGeminiResponse(text='Ready'),
            FakeGeminiResponse(text=json.dumps(report_payload(ids)))]))
        with patch.object(agent, 'Diagnostics', return_value=d):
            output = asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
        self.assertEqual(output['toolCalls'], 2)
        self.assertEqual(len(output['analysisId']), 32)
        contents = model.generate_content.call_args_list[1].kwargs['contents']
        self.assertIs(contents[1], first.candidates[0].content)
        response = contents[2].parts[0].function_response
        self.assertEqual(response.name, 'command_speed_window')
        self.assertEqual(response.response, payload)
        self.assertEqual(contents[1].parts[0].thought_signature, b'opaque-signature')

    def test_six_rejected_attempts_and_trace_identity(self):
        run = run_with()
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse([gemini_tool_call('command_speed_window', {'start': 0, 'end': 84}) for _ in range(7)]),
            FakeGeminiResponse(text=json.dumps(report_payload()))]))
        with patch.dict(agent.os.environ, {'GEMINI_DIAGNOSTIC_TRACE': '1'}), self.assertLogs(agent.logger, level='WARNING') as logs:
            output = asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
        self.assertEqual(output['toolCalls'], 6)
        final = model.generate_content.call_args.kwargs
        self.assertIsNone(final['config'].tools)
        responses = final['contents'][-2].parts
        self.assertEqual([p.function_response.response['error']['code'] for p in responses],
                         ['window_too_large'] * 6 + ['tool_budget_exhausted'])
        for line in logs.output:
            if 'Gemini tool' in line or 'Gemini finalization evidence:' in line:
                self.assertIn(output['analysisId'], line)

    def test_suggestions_respect_gaps_nulls_and_no_overlap(self):
        run = run_with([0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15], range(16))
        run['telemetry']['commanded'][1]['value'] = None
        self.assertEqual(Diagnostics(run).suggest_command_window(), {'start': 2, 'end': 5})
        for run in (run_with([], range(11)), run_with(range(4), range(6, 11)),
                    run_with([0, 1, 2, 3, 8, 9, 10], [4, 5, 6, 7])):
            d = Diagnostics(run)
            self.assertIsNone(d.suggest_command_window())
            with self.assertRaises(WindowTooLarge) as caught:
                d.command_speed_window(0, 84)
            self.assertIsNone(caught.exception.payload['error']['suggestedWindow'])
            self.assertEqual(d.evidence, {})

    def test_overlap_and_evidence_delivery(self):
        d = Diagnostics(run_with())
        result = d.dispatch('command_speed_window', {'start': 1, 'end': 9})
        self.assertTrue(result['availability']['usableCoverageOverlaps'])
        self.assertEqual(result['availability']['overlapIntervals'], [{'start': 1, 'end': 9}])
        self.assertEqual(len(agent.delivered_ids(result, d)), 6)
        self.assertLess(len(json.dumps(result)), 16000)
        for s in result['summaries']:
            self.assertEqual(s['requestedWindow'], {'start': 1, 'end': 9})
            self.assertEqual(s['count'], 9)
            self.assertEqual(s['unit'], 'm/s')
        self.assertEqual(result['semantics']['rawBagVerification']['status'], 'unavailable')
        self.assertIn('before actuator clamping', result['semantics']['meaning'])
        ids = [s['id'] for s in result['summaries']]
        agent.validate_report(json.dumps(report_payload(ids)), d, agent.delivered_ids(result, d))
        with self.assertRaises(agent.AnalysisError):
            agent.validate_report(json.dumps(report_payload(ids)), d, set())

    def test_narrative_citations_and_leading_gap(self):
        run = run_with([0.851842789, 10, 20, 29.9], range(31))
        run['duration'] = 84.750006743
        d = Diagnostics(run)
        result = d.command_speed_window(0, 30)
        delivered = agent.delivered_ids(result, d)
        gap = result['coverage'][0]
        payload = report_payload([s['id'] for s in result['summaries']])
        payload['summary'] = 'The window contains command samples; leading command unavailability: ' + gap['id']
        output = agent.validate_report(json.dumps(payload), d, delivered)
        self.assertIn(gap, output['evidence'])
        self.assertEqual(gap['leadingUncovered'], {'start': 0, 'end': 0.851842789, 'duration': 0.851842789})
        self.assertTrue(set(payload['observed_issues'][0]['evidence_ids']) <= {e['id'] for e in output['evidence']})
        with self.assertRaises(agent.AnalysisError):
            agent.validate_report(json.dumps(payload), d, delivered - {gap['id']})

    def test_unknown_narrative_citations(self):
        for field in ('summary', 'uncertainty', 'recommended_next_checks', 'finding', 'hypothesis', 'cause_uncertainty'):
            with self.subTest(field=field):
                d = Diagnostics(run_with())
                result = d.command_speed_window(0, 10)
                ids = [s['id'] for s in result['summaries']]
                payload = report_payload(ids)
                bad = 'Unsupported ev-unknown123'
                if field == 'finding':
                    payload['observed_issues'][0]['finding'] = bad
                elif field in ('hypothesis', 'cause_uncertainty'):
                    payload['possible_causes'] = [{'hypothesis': bad if field == 'hypothesis' else 'Unassessed',
                        'uncertainty': bad if field == 'cause_uncertainty' else 'Uncertain', 'evidence_ids': ids}]
                else:
                    payload[field] = bad if field == 'summary' else [bad]
                with self.assertRaises(agent.AnalysisError):
                    agent.validate_report(json.dumps(payload), d, agent.delivered_ids(result, d))

    def test_commands_start_partway(self):
        result = Diagnostics(run_with(range(6, 11))).command_speed_window(0, 10)
        self.assertEqual(result['coverage'][0]['leadingUncovered']['duration'], 6)
        self.assertEqual(result['availability']['overlapIntervals'], [{'start': 6, 'end': 10}])

    def test_internal_gap_and_nulls_are_not_bridged(self):
        run = run_with([0, 1, 2, 3, 8, 9, 10])
        run['telemetry']['commanded'][2]['value'] = None
        result = Diagnostics(run).command_speed_window(0, 10)
        c = result['coverage'][0]
        self.assertEqual(c['nullValues'], 1)
        self.assertEqual(c['internalGaps'], [{'start': 3, 'end': 8, 'duration': 5}])
        self.assertEqual(result['availability']['overlapIntervals'], [
            {'start': 0, 'end': 1}, {'start': 3, 'end': 3}, {'start': 8, 'end': 10}])
        # Bounds overlap but every speed sample is inside an absent-command gap.
        result = Diagnostics(run_with([0, 1, 2, 3, 8, 9, 10], [4, 5, 6, 7])).command_speed_window(0, 10)
        self.assertFalse(result['availability']['usableCoverageOverlaps'])

    def test_empty_and_disjoint(self):
        for commands, speeds in (([], range(11)), (range(5), range(6, 11))):
            result = Diagnostics(run_with(commands, speeds)).command_speed_window(0, 10)
            self.assertFalse(result['availability']['usableCoverageOverlaps'])
        empty = Diagnostics(run_with([])).command_speed_window(0, 10)
        self.assertIsNone(empty['coverage'][0]['firstTimestamp'])
        self.assertEqual(empty['coverage'][0]['entireRunUncovered']['duration'], 10)

    def test_explicit_bounded_window_required(self):
        d = Diagnostics(run_with())
        for start, end in ((None, 1), (True, 2), (1, 1), (-1, 4), (0, 31), (0, float('nan'))):
            with self.assertRaises(ValueError):
                d.command_speed_window(start, end)

    def test_six_comparison_calls_then_tools_disabled(self):
        run = run_with()
        d = Diagnostics(run)
        result = d.command_speed_window(1, 9)
        ids = [s['id'] for s in result['summaries']]
        model = SimpleNamespace(generate_content=AsyncMock(side_effect=[
            FakeGeminiResponse([gemini_tool_call('command_speed_window', {'start': 1, 'end': 9}) for _ in range(7)]),
            FakeGeminiResponse(text=json.dumps(report_payload(ids)))]))
        with patch.object(agent, 'Diagnostics', return_value=d), patch.object(d, 'dispatch', wraps=d.dispatch) as dispatch:
            output = asyncio.run(agent.investigate(run, SimpleNamespace(models=model), 'mock'))
        self.assertEqual(dispatch.call_count, 6)
        self.assertEqual(output['toolCalls'], 6)
        final = model.generate_content.call_args.kwargs
        self.assertIsNone(final['config'].tools)
        self.assertEqual(final['contents'][-2].parts[-1].function_response.response['error']['code'], 'tool_budget_exhausted')


if __name__ == '__main__':
    unittest.main()
