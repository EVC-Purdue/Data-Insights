"""Read-only adapter for AutonomousSimulator's public viewer API (no GPL code copied)."""
import hashlib
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

SOURCE_REVISION = 'a9bfce0583e337b11f414e6057c1eab69182d34e'
SOURCE = f'https://github.com/EVC-Purdue/AutonomousSimulator/blob/{SOURCE_REVISION}'
MAX_BYTES = 32 * 1024 * 1024


class SimulatorError(ValueError):
    pass


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,159}', value):
        raise SimulatorError('Invalid simulator identifier')
    return value


def base_url():
    base = os.environ.get('SIMULATOR_URL', 'https://evc.researchviewer.org').rstrip('/')
    url = urlsplit(base)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise SimulatorError('SIMULATOR_URL must be an HTTP(S) base URL without credentials or query')
    return base


def get_json(path):
    # Paths are constructed here, never accepted as arbitrary model/user URLs.
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as client:
            with client.stream('GET', base_url() + path) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES or time.monotonic() - started > 30:
                        raise SimulatorError('Simulator response exceeded the size or duration limit')
        return json.loads(data)
    except httpx.TimeoutException:
        raise SimulatorError('Simulator request timed out; cached runs remain available') from None
    except httpx.HTTPStatusError as exc:
        raise SimulatorError(f'Simulator returned HTTP {exc.response.status_code}') from None
    except (httpx.HTTPError, UnicodeError, json.JSONDecodeError):
        raise SimulatorError('Simulator unavailable or returned invalid JSON; cached runs remain available') from None


def jobs():
    data = get_json('/api/jobs')
    if not isinstance(data, list) or any(not isinstance(j, dict) or 'id' not in j for j in data):
        raise SimulatorError('Unexpected simulator job list')
    return data


def episode_rows(detail):
    """The API exposes episode keys in lap cells and clip groups, not /episodes."""
    rows = {}
    def visit(node, labels):
        if isinstance(node, dict):
            if isinstance(node.get('key'), str):
                identifier(node['key'])
                rows[node['key']] = {**node, 'label': ' / '.join(labels)}
            else:
                for key, value in node.items():
                    visit(value, labels + [key])
        elif isinstance(node, list):
            for value in node:
                visit(value, labels)
    visit(detail.get('breakdown', {}), [])
    return list(rows.values())


def job_detail(job_id):
    data = get_json('/api/jobs/' + identifier(job_id))
    if not isinstance(data, dict) or not isinstance(data.get('job'), dict) or data['job'].get('id') != job_id:
        raise SimulatorError('Unexpected simulator job detail')
    return data


# Public viewer units, not raw logger units: yaw_rate has already become deg/s.
SIGNALS = {
    'speed': ('m/s', 'simulation_ground_truth'),
    'x': ('m', 'simulation_ground_truth'), 'y': ('m', 'simulation_ground_truth'),
    'yaw': ('rad', 'simulation_ground_truth'),
    'wheel': ('deg', 'simulation_ground_truth'), 'wheel_l': ('deg', 'simulation_ground_truth'),
    'wheel_r': ('deg', 'simulation_ground_truth'), 'column': ('deg', 'simulation_ground_truth'),
    'cte': ('m', 'truth_derived'), 'ay': ('m/s^2', 'simulation_ground_truth'),
    'ay_mps2': ('m/s^2', 'truth_derived'), 'loc_err': ('m', 'estimate_error_against_simulation_truth'),
    'yaw_rate': ('deg/s', 'simulation_ground_truth'), 'cmd_speed': ('m/s', 'command'),
    'phase': ('enum:0=warmup,1=context,2=autonomous', 'simulation_state'),
    'beta_deg': ('deg', 'truth_derived'), 'rear_slip_deg': ('deg', 'truth_derived'),
    'front_slip_deg': ('deg', 'truth_derived'), 'rear_slip_ratio': ('%', 'truth_derived'),
    'lat_front_pct': ('%', 'truth_derived'), 'lat_rear_pct': ('%', 'truth_derived'),
    'slide_pct': ('%', 'truth_derived'), 'slide_front': ('boolean', 'truth_derived'),
    'slide_rear': ('boolean', 'truth_derived'), 'cost': ('objective (configuration dependent)', 'estimate'),
}


def map_episode(job, episode, row, base):
    if not isinstance(episode, dict) or not isinstance(episode.get('log'), dict):
        raise SimulatorError('Unexpected simulator episode format')
    key = identifier(episode.get('key'))
    if key != row['key']:
        raise SimulatorError('Simulator returned a different episode')
    log = episode['log']
    times = log.get('t', [])
    if not isinstance(times, list) or len(times) > 200000 or any(not number(t) for t in times):
        raise SimulatorError('Invalid simulator timestamps')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise SimulatorError('Simulator timestamps must increase')
    outcome = episode.get('outcome') or {}
    if not isinstance(outcome, dict):
        raise SimulatorError('Invalid simulator outcome')
    if outcome.get('status') in ('queued', 'running') or row.get('status') in ('queued', 'running'):
        raise SimulatorError('Select a completed episode')
    handoff = outcome.get('handoff_t')
    known_handoff = number(handoff)
    source_url = f'{base}/api/episodes/{identifier(job["id"])}/{key}'
    measurements = {}
    for name, values in log.items():
        if name == 't' or not isinstance(values, list):
            continue  # nested cost terms are retained in the original cached payload
        if len(values) != len(times) or any(v is not None and not number(v) for v in values):
            raise SimulatorError(f'Invalid simulator signal: {name}')
        unit, kind = SIGNALS.get(name, (None, 'unknown'))
        measurements[name] = {'unit': unit, 'kind': kind, 'source': source_url + '#log.' + name,
                              'samples': [{'time': t, 'value': v} for t, v in zip(times, values)]}
    telemetry = {name: [] for name in ('speed', 'throttle', 'steering', 'acceleration', 'gps', 'commanded')}
    for target, name in [('speed', 'speed'), ('steeringAngle', 'wheel'),
                         ('lateralAcceleration', 'ay_mps2')]:
        telemetry[target] = measurements.get(name, {}).get('samples', [])
    telemetry['commanded'] = [{'time': t, 'target': command,
                               'actual': log['speed'][i] if 'speed' in log else None}
                              for i, (t, command) in enumerate(zip(times, log.get('cmd_speed', [])))]
    # Position is simulation truth, deliberately not passed off as GPS.
    telemetry['simPosition'] = [{'time': t, 'x': x, 'y': y}
                                for t, x, y in zip(times, log.get('x', []), log.get('y', []))
                                if number(x) and number(y)]
    run_id = 'sim-' + hashlib.sha256(f'{base}/{job["id"]}/{key}'.encode()).hexdigest()[:24]
    return {'id': run_id, 'name': f'Sim {job["id"]} / {key[:10]}', 'source': 'simulator',
            'date': job.get('finished_at'), 'duration': times[-1] - times[0] if times else 0,
            'status': outcome.get('status', row.get('status', 'Completed job; episode status unavailable')),
            'speedLabel': 'Simulation ground-truth forward speed',
            'controller': {'health': 'Unavailable', 'mode': None, 'frequency': None,
                           'trackingError': None, 'messages': None},
            'telemetry': telemetry,
            'diagnostic': {'schemaVersion': 1, 'measurements': measurements,
                'metadata': {'source': source_url, 'jobId': job['id'], 'episodeId': key,
                    'importedAt': datetime.now(timezone.utc).isoformat(),
                    'job': job, 'episodeSelection': row,
                    'versions': {'engine': job.get('engine_version'), 'tier': job.get('tier_version'),
                                 'code': job.get('recipe', {}).get('source'),
                                 'configuration': job.get('recipe'), 'adapterReference': SOURCE_REVISION},
                    'time': {'unit': 's', 'basis': 'handoff_relative' if known_handoff else 'simulator_time_handoff_unknown',
                             'handoffSimulatorTime': handoff if known_handoff else None,
                             'start': times[0] if times else None, 'end': times[-1] if times else None,
                             'note': 'API subtracts outcome.handoff_t, or 0 when absent. No wall-clock alignment.'},
                    'contextValid': episode.get('context_valid'), 'scenario': episode.get('scenario'),
                    'limitations': ['Viewer telemetry is rounded and decimated to about 20 Hz.',
                                    'Absent outcome/handoff metadata cannot be inferred from the synthetic handoff event.']},
                'metrics': {name: {'value': value,
                    'unit': {'cte_p90': 'm', 'peak_cte_after_m': 'm', 'recovery_s': 's', 'recovered': 'boolean'}.get(name),
                    'source': source_url + '#metrics.' + name, 'kind': 'simulator_reported_metric',
                    'definition': SOURCE + '/harness/metrics.py', 'timeWindow': 'Upstream autonomous evaluation window'}
                    for name, value in episode.get('metrics', {}).items()}, 'outcome': outcome,
                'upstreamEvents': episode.get('events', []), 'unsafe': episode.get('unsafe', {}),
                'latLimit': episode.get('lat_limit'), 'localizationMetrics': episode.get('loc')}}


class EpisodeCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def save(self, run, episode):
        self.directory.mkdir(parents=True, exist_ok=True)
        # Cache the untouched JSON response too: unknown future fields are not discarded.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory, suffix='.tmp', delete=False) as f:
            tmp = Path(f.name)
            json.dump({'run': run, 'originalEpisode': episode}, f, allow_nan=False)
        try:
            os.replace(tmp, self.directory / (run['id'] + '.json'))
        finally:
            tmp.unlink(missing_ok=True)

    def load(self):
        loaded, errors = [], []
        for path in self.directory.glob('sim-*.json'):
            try:
                if path.stat().st_size > MAX_BYTES * 8:
                    raise ValueError('Oversize cache')
                run = json.loads(path.read_text(encoding='utf-8'))['run']
                if run['id'] != path.stem or run['source'] != 'simulator' or run['diagnostic']['schemaVersion'] != 1:
                    raise ValueError('Invalid cache')
                loaded.append(run)
            except (OSError, ValueError, KeyError, TypeError):
                errors.append(f'Could not read cached episode {path.name}')
        return loaded, errors


def import_episode(job_id, episode_id, cache):
    detail = job_detail(job_id)
    if detail['job'].get('status') != 'done':
        raise SimulatorError('Select a completed simulator job')
    row = next((r for r in episode_rows(detail) if r['key'] == identifier(episode_id)), None)
    if row is None:
        raise SimulatorError('Episode does not belong to the selected job')
    episode = get_json(f'/api/episodes/{job_id}/{episode_id}')
    run = map_episode(detail['job'], episode, row, base_url())
    cache.save(run, episode)
    return run
