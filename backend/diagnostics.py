"""Small read-only run format and Python-calculated evidence. No model arithmetic."""
import hashlib
import json
import math
from copy import deepcopy
from statistics import median

from simulator import SOURCE, number


def run_format(run):
    if 'diagnostic' in run:
        return run['diagnostic']
    live = run['source'] == 'live'
    definitions = {'speed': ('m/s', 'estimate' if live else 'sensor_measurement', '/odom' if live else '/e_comms/kart_speed_m_per_s'),
                   'throttle': ('raw PWM', 'command', '/e_comms/throttle_pwm'),
                   'steering': ('raw PWM', 'command', '/e_comms/steering_pwm'),
                   'acceleration': ('m/s^2', 'sensor_measurement', '/imu linear_acceleration.x'),
                   'commanded': ('m/s', 'command', 'unavailable')}
    measurements = {name: {'unit': unit, 'kind': kind, 'source': source, 'samples': run['telemetry'].get(name, [])}
                    for name, (unit, kind, source) in definitions.items()}
    points = run['telemetry'].get('gps', [])
    for axis in ('x', 'y'):
        measurements['position_' + axis] = {'unit': 'm', 'kind': 'estimate', 'source': '/odom' if live else '/gps',
            'samples': [{'time': p['time'], 'value': p.get(axis)} for p in points]}
    times = [p['time'] for m in measurements.values() for p in m['samples']]
    start = min(times) if times else None
    end = max(times) if times else None
    if not live and number(run.get('duration')):
        start = min(0, start) if start is not None else 0
        end = max(run['duration'], end) if end is not None else run['duration']
    return {'schemaVersion': 1, 'measurements': measurements,
            'metadata': {'source': run['source'], 'runId': run['id'], 'date': run.get('date'),
                'time': {'unit': 's', 'basis': 'laptop_arrival_relative' if live else 'bag_log_relative',
                         'start': start, 'end': end},
                'limitations': ['No reference truth: real-world localization error cannot be calculated.',
                                'Live diagnostics use a snapshot of the retained five-minute window.' if live else
                                'Signals are asynchronous; unavailable samples are not fabricated.']},
            'metrics': {}, 'outcome': {}, 'upstreamEvents': [], 'unsafe': {}, 'latLimit': None}


def evidence_id(value):
    return 'ev-' + hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]


class Diagnostics:
    def __init__(self, run):
        self.run_id = run['id']
        self.data = run_format(run)
        self.evidence = {}

    def record(self, value):
        item = {**value, 'id': evidence_id(value)}
        self.evidence[item['id']] = item
        return item

    def metadata(self):
        return deepcopy(self.data['metadata'])

    def signals(self):
        return [{'name': name, **{k: v for k, v in m.items() if k != 'samples'},
                 'samples': len(m['samples']), 'missing': sum(not number(p.get('value')) for p in m['samples'])}
                for name, m in self.data['measurements'].items()]

    def coverage(self, signal):
        if signal not in self.data['measurements']:
            raise ValueError('Unknown signal')
        m = self.data['measurements'][signal]
        samples = m['samples']
        times = sorted({p['time'] for p in samples if number(p.get('time'))})
        valid_times = sorted({p['time'] for p in samples if number(p.get('time')) and number(p.get('value'))})
        deltas = [b - a for a, b in zip(times, times[1:])]
        cadence = median(deltas) if len(deltas) >= 3 else None
        gaps = [{'start': a, 'end': b, 'duration': b - a} for a, b in zip(times, times[1:])
                if cadence is not None and b - a > 3 * cadence + 1e-9]
        bounds = self.data['metadata']['time']
        start, end = bounds.get('start'), bounds.get('end')
        def interval(a, b):
            return {'start': a, 'end': b, 'duration': b - a} if number(a) and number(b) and b > a else None
        first, last = (times[0], times[-1]) if times else (None, None)
        # Do not assign an empty series two overlapping leading/trailing gaps.
        return self.record({'type': 'signal_coverage', 'signal': signal, 'unit': m['unit'],
            'kind': m['kind'], 'source': m['source'], 'timeBasis': bounds,
            'state': 'empty' if not samples else 'no_finite_values' if not valid_times else 'sampled',
            'samples': len(samples), 'nullValues': sum(p.get('value') is None for p in samples),
            'invalidValues': sum(p.get('value') is not None and not number(p.get('value')) for p in samples),
            'invalidTimestamps': sum(not number(p.get('time')) for p in samples),
            'firstTimestamp': first, 'lastTimestamp': last,
            'firstFiniteTimestamp': valid_times[0] if valid_times else None,
            'lastFiniteTimestamp': valid_times[-1] if valid_times else None,
            'leadingUncovered': interval(start, first), 'trailingUncovered': interval(last, end),
            'entireRunUncovered': interval(start, end) if not times else None,
            'cadenceSeconds': cadence, 'gapThresholdSeconds': 3 * cadence if cadence is not None else None,
            'internalGapCount': len(gaps), 'internalGapSeconds': math.fsum(g['duration'] for g in gaps),
            'internalGaps': sorted(gaps, key=lambda g: (-g['duration'], g['start']))[:3],
            'gapsTruncated': len(gaps) > 3,
            'method': 'Timestamp gaps > 3x median positive spacing (>=3 spacings), tolerance 1e-9 s; largest 3 shown. Nulls are values at present timestamps. Coverage gaps alone do not establish sensor failure.'})

    def overview(self):
        names = list(self.data['measurements'])
        preferred = ['speed', 'acceleration', 'ay_mps2', 'steering', 'throttle', 'cmd_speed', 'commanded']
        ordered = [n for n in preferred if n in names] + [n for n in names if n not in preferred]
        metadata = self.metadata()
        return {'metadata': {k: metadata[k] for k in ('source', 'time', 'limitations') if k in metadata},
                'coverage': [self.coverage(n) for n in ordered[:12]], 'omittedSignals': ordered[12:],
                'note': 'Coverage is timestamp availability, not a sensor-health verdict. Use signal_coverage for omitted signals and time_window_summary for measurements/commands.'}

    def summary(self, signal, start=None, end=None):
        if signal not in self.data['measurements']:
            raise ValueError('Unknown signal')
        for v in (start, end):
            if v is not None and not number(v):
                raise ValueError('Window bounds must be finite numbers or null')
        if start is not None and end is not None and start > end:
            raise ValueError('Window start must not exceed end')
        m = self.data['measurements'][signal]
        samples = [p for p in m['samples'] if (start is None or p['time'] >= start) and (end is None or p['time'] <= end)]
        valid = [p for p in samples if number(p.get('value'))]
        values = [p['value'] for p in valid]
        lo = min(valid, key=lambda p: p['value']) if valid else None
        hi = max(valid, key=lambda p: p['value']) if valid else None
        return self.record({'type': 'window_summary', 'signal': signal, 'unit': m['unit'], 'kind': m['kind'],
            'requestedWindow': {'start': start, 'end': end},
            'source': m['source'], 'timeBasis': self.data['metadata']['time'],
            'start': samples[0]['time'] if samples else start, 'end': samples[-1]['time'] if samples else end,
            'count': len(valid), 'missing': len(samples) - len(valid), 'min': lo, 'max': hi,
            'mean': math.fsum(values) / len(values) if values else None,
            'meanAbsolute': math.fsum(abs(v) for v in values) / len(values) if values else None,
            'positiveCount': sum(v > 0 for v in values), 'negativeCount': sum(v < 0 for v in values),
            'zeroCount': sum(v == 0 for v in values),
            'rms': math.hypot(*values) / math.sqrt(len(values)) if values else None,
            'threshold': None, 'method': 'Sample-weighted finite values; no interpolation; no failure threshold. Signed mean can cancel during reversals; meanAbsolute and rms are magnitudes, not distance.'})

    def significant_coverage(self):
        """Deterministic finalization context, not another model-requested tool."""
        bounds = self.data['metadata']['time']
        duration = max(0, (bounds.get('end') or 0) - (bounds.get('start') or 0))
        items = []
        for name in self.data['measurements']:
            c = self.coverage(name)
            threshold = max(1.0, duration * 0.05, 3 * (c['cadenceSeconds'] or 0))
            intervals = [dict(kind=kind, **c[kind]) for kind in ('leadingUncovered', 'trailingUncovered', 'entireRunUncovered')
                         if c[kind] and c[kind]['duration'] >= threshold]
            intervals += [dict(kind='internalGap', **gap) for gap in c['internalGaps'] if gap['duration'] >= threshold]
            if intervals or c['nullValues'] or c['invalidValues'] or c['state'] in ('empty', 'no_finite_values'):
                items.append({'type': 'coverage_limitation', 'signal': name, 'source': c['source'],
                    'timeBasis': bounds, 'state': c['state'], 'nullValues': c['nullValues'],
                    'invalidValues': c['invalidValues'], 'intervals': intervals,
                    'significanceSeconds': threshold,
                    'meaning': 'Imported signal availability only; source-topic inventory not checked. Not proof of sensor failure.'})
        items.sort(key=lambda c: -max((i['duration'] for i in c['intervals']), default=0))
        return {'limitations': [self.record(item) for item in items[:8]], 'omittedCount': max(0, len(items) - 8),
                'rule': 'Uncovered interval >= max(1 s, 5% run duration, 3 cadence intervals); also empty/all-invalid signals and explicit invalid values. Largest 8 signal limitations shown.'}

    def events(self):
        found = []
        measurements = self.data['measurements']
        phase = {p['time']: p['value'] for p in measurements.get('phase', {}).get('samples', [])}
        # Only use a threshold actually returned by the episode API, never assume defaults apply.
        limit = (self.data.get('latLimit') or {}).get('envelope')
        lateral = measurements.get('ay_mps2')
        if lateral and number(limit) and limit > 0:
            active = []
            def flush():
                if active:
                    peak = max(active, key=lambda p: abs(p['value']))
                    found.append(self.record({'type': 'observed_threshold_exceedance', 'signal': 'ay_mps2',
                        'start': active[0]['time'], 'end': active[-1]['time'], 'peak': peak,
                        'unit': lateral['unit'], 'source': lateral['source'], 'kind': lateral['kind'],
                        'timeBasis': self.data['metadata']['time'],
                        'threshold': {'value': limit, 'operator': 'abs(value) >', 'unit': 'm/s^2',
                                      'provenance': 'episode.lat_limit.envelope; ' + SOURCE + '/harness/metrics.py',
                                      'continuity': 'Data-Insights viewer heuristic: break at missing/non-auto samples or gaps > 0.15 s'},
                        'description': 'Filtered lateral acceleration exceeds the supplied envelope on autonomous viewer samples; not a root cause.'}))
                    active.clear()
            for p in lateral['samples']:
                if number(p['value']) and phase.get(p['time']) == 2 and abs(p['value']) > limit:
                    if active and p['time'] - active[-1]['time'] > 0.15:
                        flush()
                    active.append(p)
                else:
                    flush()
            flush()
        for name, m in measurements.items():
            missing = [p for p in m['samples'] if not number(p.get('value'))]
            if missing:
                found.append(self.record({'type': 'missing_data', 'signal': name, 'start': missing[0]['time'],
                    'end': missing[-1]['time'], 'count': len(missing), 'unit': m['unit'], 'source': m['source'],
                    'threshold': {'provenance': 'Data-Insights: explicit null/nonfinite values; no interpolation'},
                    'description': 'Missing samples within this span; not necessarily one continuous gap.'}))
        for event in self.data.get('upstreamEvents', []):
            if isinstance(event, dict) and event.get('kind') != 'handoff':
                found.append(self.record({'type': 'simulator_label', 'label': event.get('kind'),
                    'start': event.get('t'), 'end': event.get('t'), 'unit': 's',
                    'source': self.data['metadata']['source'] + '#events',
                    'threshold': {'provenance': 'Simulator-provided label; not independently reproduced'},
                    'description': 'Reports an existing simulator outcome, not an independent diagnosis.'}))
        row = self.data['metadata'].get('episodeSelection', {})
        outcome = self.data.get('outcome', {})
        label = outcome.get('cause') or row.get('cause')
        if label and not any(e.get('label') == label for e in found):
            found.append(self.record({'type': 'simulator_label', 'label': label, 'start': None, 'end': None,
                'unit': None, 'source': self.data['metadata']['source'] + '#outcome-or-job-breakdown',
                'threshold': {'provenance': 'Simulator-provided label; failure time unavailable'},
                'description': 'Reports an existing simulator label only; no causal inference.'}))
        for criterion, intervals in self.data.get('unsafe', {}).items():
            for start, end in intervals:
                found.append(self.record({'type': 'simulator_unsafe_interval', 'label': criterion, 'start': start, 'end': end,
                    'unit': 's', 'source': self.data['metadata']['source'] + '#unsafe',
                    'threshold': {'provenance': 'Upstream full-rate calculation; ' + SOURCE + '/harness/metrics.py'},
                    'description': 'Existing simulator safety annotation; not independently reproduced.'}))
        independent = any(e['type'] == 'observed_threshold_exceedance' for e in found)
        return {'events': found[:80], 'totalEvents': len(found), 'truncated': len(found) > 80,
                'outcomeCheck': {'simulatorLabel': label, 'independentLateralExceedance': independent,
                    'conclusion': 'No root-cause validation: lateral exceedance cannot establish localization, spin, or off-track failure.'},
                'limitations': ['No detected event is not proof of a safe run.',
                    'Missing reference truth, odometry/command ages and full-rate footprint data prevent reproducing all failure rules.']}

    def dispatch(self, name, args):
        if not isinstance(args, dict):
            raise ValueError('Tool arguments must be an object')
        expected = {'run_metadata': set(), 'available_signals': set(), 'detected_events': set(),
                    'run_overview': set(), 'signal_coverage': {'signal'},
                    'time_window_summary': {'signal', 'start', 'end'}}
        if name not in expected or set(args) != expected[name]:
            raise ValueError('Unknown tool or invalid argument keys; tools are restricted to the selected run')
        if name in ('time_window_summary', 'signal_coverage'):
            if not isinstance(args['signal'], str):
                raise ValueError('Signal must be a string')
            return self.coverage(**args) if name == 'signal_coverage' else self.summary(**args)
        return {'run_metadata': self.metadata, 'available_signals': self.signals, 'detected_events': self.events,
                'run_overview': self.overview}[name]()

    def report(self):
        events = self.events()
        return {'runId': self.run_id, 'metadata': self.metadata(), 'signals': self.signals(),
                'summaries': [self.summary(s['name']) for s in self.signals() if s['samples']],
                **events, 'upstreamMetrics': self.data.get('metrics', {}),
                'upstreamMetricProvenance': 'Simulator-reported metrics, not recomputed from decimated telemetry; ' + SOURCE + '/harness/metrics.py'}
