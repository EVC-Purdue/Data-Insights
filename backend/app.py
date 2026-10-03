"""Laptop-only, read-only telemetry viewer. No ROS installation required."""
import argparse
import json
import math
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener, ProxyHandler

from flask import Flask, jsonify, send_from_directory, request
from mcap_ros2.reader import read_ros2_messages

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=str(ROOT / 'frontend' / 'dist'))
lock = threading.Lock()
runs = {}
connection = {'configured': False, 'connected': False, 'error': None, 'lastResponse': None, 'lastAdvance': None}


@app.after_request
def local_cors(response):
    if request.path.startswith('/api/') and request.headers.get('Origin') in {
        'http://localhost:5173', 'http://127.0.0.1:5173',
    }:
        response.headers['Access-Control-Allow-Origin'] = request.headers['Origin']
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.vary.add('Origin')
    return response


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    return value


def new_run(key, name, source):
    return {'id': key, 'name': name, 'source': source, 'duration': 0,
            'date': None,
            'controller': {'health': 'Unavailable', 'mode': None, 'frequency': None,
                           'trackingError': None, 'messages': None},
            'telemetry': {'speed': [], 'throttle': [], 'steering': [], 'gps': [],
                          'acceleration': [], 'commanded': []},
            'speedLabel': 'Wheel speed', 'status': 'Recorded'}


def import_bag(path):
    key = path.stem
    run = new_run(key, path.parent.name, 'recording')
    start = None
    status_times = []
    topics = ['/e_comms/kart_speed_m_per_s', '/e_comms/throttle_pwm', '/e_comms/steering_pwm', '/gps']
    # Use a common bag log-time origin, retaining individual message timestamps.
    for event in read_ros2_messages(str(path)):
        stamp = event.log_time_ns
        if start is None:
            start = stamp
            run['date'] = datetime.fromtimestamp(stamp / 1e9, timezone.utc).isoformat()
        t = (stamp - start) / 1e9
        run['duration'] = max(run['duration'], t)
        topic = event.channel.topic
        if topic == '/mpc/status':
            status_times.append(t)
        if topic == '/imu':
            msg = event.ros_msg
            value = float(msg.linear_acceleration.x)
            if msg.linear_acceleration_covariance[0] != -1 and math.isfinite(value):
                run['telemetry']['acceleration'].append({'time': t, 'value': value})
        if topic not in topics:
            continue
        msg = event.ros_msg
        if topic == '/gps':
            p = msg.pose.pose.position
            if math.isfinite(p.x) and math.isfinite(p.y):
                run['telemetry']['gps'].append({'time': t, 'x': p.x, 'y': p.y})
        else:
            signal = {topics[0]: 'speed', topics[1]: 'throttle', topics[2]: 'steering'}[topic]
            value = float(msg.data)
            if math.isfinite(value):
                run['telemetry'][signal].append({'time': t, 'value': value})
    if start is None:
        raise ValueError('Recording contains no decoded messages')
    for series in run['telemetry'].values():
        series.sort(key=lambda p: p['time'])
    run['controller']['messages'] = len(status_times)
    if len(status_times) > 1 and max(status_times) > min(status_times):
        run['controller']['frequency'] = (len(status_times) - 1) / (max(status_times) - min(status_times))
    return run


def summarize(run):
    series = run['telemetry']['speed']
    distance = sum((abs(a['value']) + abs(b['value'])) / 2 * (b['time'] - a['time'])
                   for a, b in zip(series, series[1:])) if len(series) > 1 else None
    return {**{k: v for k, v in run.items() if k != 'telemetry'},
            'distance': distance,
            'currentSpeed': series[-1]['value'] if series else None,
            'maxSpeed': max((p['value'] for p in series), default=None)}


def thin(series, limit=1800):
    # Keep bucket extrema for scalar signals so short spikes survive display reduction.
    if len(series) <= limit:
        return series
    step = math.ceil(len(series) / (limit // 2))
    out = [series[0]]
    for i in range(0, len(series), step):
        bucket = series[i:i + step]
        if 'value' in bucket[0]:
            out.extend(sorted([min(bucket, key=lambda p: p['value']), max(bucket, key=lambda p: p['value'])], key=lambda p: p['time']))
        else:
            out.append(bucket[0])
    out.append(series[-1])
    return out


@app.get('/api/health')
def health():
    with lock:
        c = dict(connection)
    now = time.time()
    c['responseAge'] = now - c['lastResponse'] if c['lastResponse'] else None
    c['sourceAge'] = now - c['lastAdvance'] if c['lastAdvance'] else None
    c['stale'] = c['sourceAge'] is None or c['sourceAge'] > 2
    return jsonify(c)


@app.get('/api/runs')
def list_runs():
    with lock:
        return jsonify(clean([summarize(r) for r in runs.values()]))


@app.get('/api/runs/<key>/telemetry')
def telemetry(key):
    with lock:
        run = runs.get(key)
        if run is None:
            return jsonify(error='Run not found'), 404
        return jsonify(clean({**summarize(run), 'telemetry': {k: thin(v) for k, v in run['telemetry'].items()}}))


@app.get('/')
def index():
    if not (ROOT / 'frontend/dist/index.html').exists():
        return 'Build the frontend first: cd frontend && npm install && npm run build', 503
    return send_from_directory(app.static_folder, 'index.html')


@app.get('/assets/<path:name>')
def assets(name):
    return send_from_directory(Path(app.static_folder) / 'assets', name)


def collect(base, db_path):
    # Disable proxy environment variables for the explicit local/Tailscale destination.
    opener = build_opener(ProxyHandler({}))
    db = sqlite3.connect(db_path)
    db.execute('CREATE TABLE IF NOT EXISTS snapshots (received REAL, source_stamp INTEGER, payload TEXT)')
    db.commit()
    last_stamp = None
    origin = None
    run = new_run('live', 'Jetson · current session', 'live')
    run['speedLabel'] = 'EKF forward speed (/odom)'
    run['status'] = 'Waiting for Jetson'
    with lock:
        runs['live'] = run
        connection['configured'] = True
    while True:
        started = time.monotonic()
        try:
            with opener.open(base.rstrip('/') + '/odom', timeout=1.5) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise ValueError('/odom did not return an object')
            stamp = int(data.get('stamp_ns', 0))
            now = time.time()
            with lock:
                connection.update(connected=True, error=None, lastResponse=now)
            if stamp <= 0:
                raise ValueError('API reachable, but no timestamped odometry received yet')
            if stamp != last_stamp:
                # Arrival time for the live graph avoids mixing laptop and ROS clocks.
                origin = origin or now
                t = now - origin
                db.execute('INSERT INTO snapshots VALUES (?, ?, ?)', (now, stamp, json.dumps(clean(data))))
                db.commit()
                with lock:
                    connection['lastAdvance'] = now
                    run['duration'] = t
                    run['status'] = str(data.get('state', 'Unknown'))
                    speed = data.get('speed', data.get('vx'))
                    if isinstance(speed, (int, float)) and math.isfinite(speed):
                        run['telemetry']['speed'].append({'time': t, 'value': speed})
                    x, y = data.get('x'), data.get('y')
                    if all(isinstance(v, (int, float)) and math.isfinite(v) for v in [x, y]):
                        run['telemetry']['gps'].append({'time': t, 'x': x, 'y': y})
                    # /odom has no PWM feedback: leave those plots unavailable in live mode.
                    for name, series in run['telemetry'].items():
                        run['telemetry'][name] = [p for p in series if p['time'] >= t - 300]
                last_stamp = stamp
        except Exception as exc:
            with lock:
                connection.update(connected=False, error=str(exc))
        time.sleep(max(0.01, 0.25 - (time.monotonic() - started)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'src/data')
    parser.add_argument('--jetson-url', help='Existing master API, e.g. http://127.0.0.1:8000 through SSH')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()
    for path in sorted(args.data_dir.rglob('*.mcap')):
        try:
            run = import_bag(path)
            runs[run['id']] = run
            print(f"Loaded {path.name}: {run['duration']:.1f}s, {len(run['telemetry']['speed'])} speed samples", flush=True)
        except Exception as exc:
            print(f'SKIPPED {path}: {exc}', flush=True)
    if args.jetson_url:
        if not args.jetson_url.startswith(('http://', 'https://')):
            parser.error('--jetson-url must start with http:// or https://')
        dest = ROOT / 'recordings'
        dest.mkdir(exist_ok=True)
        db = dest / f'jetson-{time.time_ns()}.sqlite3'
        print(f'Live snapshots saved to {db}', flush=True)
        threading.Thread(target=collect, args=(args.jetson_url, db), daemon=True).start()
    app.run(host='127.0.0.1', port=args.port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
