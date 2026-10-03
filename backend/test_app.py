import json
import sqlite3
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from backend import app as mod

class TelemetryTests(unittest.TestCase):
    def test_recording_and_api(self):
        path = next((mod.ROOT / 'src/data').rglob('*.mcap'))
        run = mod.import_bag(path)
        self.assertEqual(len(run['telemetry']['speed']), 8475)
        self.assertEqual(len(run['telemetry']['gps']), 848)
        mod.runs[run['id']] = run
        with mod.app.test_client() as c:
            self.assertEqual(c.get('/api/runs').status_code, 200)
            data = c.get('/api/runs/' + run['id'] + '/telemetry').get_json()
            self.assertLessEqual(len(data['telemetry']['speed']), 1802)
            self.assertEqual(data['maxSpeed'], max(p['value'] for p in run['telemetry']['speed']))
            self.assertEqual(len(run['telemetry']['acceleration']), 5842)
            self.assertAlmostEqual(data['distance'], 34.798062667, places=5)
            self.assertEqual(data['controller']['messages'], 4621)
            self.assertIsNone(data['controller']['trackingError'])
            self.assertEqual(data['telemetry']['commanded'], [])
            self.assertTrue(data['date'].startswith('2026-05-19'))
            for origin in ['http://localhost:5173', 'http://127.0.0.1:5173']:
                response = c.get('/api/runs', headers={'Origin': origin})
                self.assertEqual(response.headers['Access-Control-Allow-Origin'], origin)
            self.assertNotIn('Access-Control-Allow-Origin', c.get('/api/runs', headers={'Origin': 'https://example.com'}).headers)
            self.assertEqual(c.get('/api/runs/missing/telemetry').status_code, 404)
            with c.get('/') as response:
                self.assertEqual(response.status_code, 200)

    def test_live_fresh_stale_disconnect_and_persistence(self):
        class Handler(BaseHTTPRequestHandler):
            stamp = 100
            broken = False
            def do_GET(self):
                if self.broken:
                    self.send_error(503)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'stamp_ns': self.stamp, 'speed': 3.5, 'x': 2, 'y': 4, 'state': 'AUTONOMOUS'}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        # Collector runs until process exit; use a dedicated temporary file.
        dbpath = Path(tempfile.mkdtemp()) / 'live.sqlite3'
        threading.Thread(target=mod.collect, args=(f'http://127.0.0.1:{server.server_port}', dbpath), daemon=True).start()
        def wait_for(predicate):
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(.05)
            self.fail('Condition timed out')
        wait_for(lambda: mod.connection['lastAdvance'] is not None)
        with mod.app.test_client() as c:
            self.assertFalse(c.get('/api/health').get_json()['stale'])
            self.assertEqual(c.get('/api/runs/live/telemetry').get_json()['currentSpeed'], 3.5)
            # Unchanged source timestamps must not create fresh samples.
            wait_for(lambda: c.get('/api/health').get_json()['stale'])
            self.assertEqual(len(mod.runs['live']['telemetry']['speed']), 1)
            Handler.stamp += 1
            wait_for(lambda: len(mod.runs['live']['telemetry']['speed']) == 2)
            Handler.broken = True
            wait_for(lambda: not c.get('/api/health').get_json()['connected'])
            Handler.broken = False
            Handler.stamp += 1
            wait_for(lambda: c.get('/api/health').get_json()['connected'] and len(mod.runs['live']['telemetry']['speed']) == 3)
        with sqlite3.connect(dbpath) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 3)
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    unittest.main()
