# Autonomous Kart Telemetry

The React + Vite dashboard lives in [`frontend/`](frontend/). Flask in [`backend/`](backend/) reads MCAP recordings from `src/data` into memory and serves them to the dashboard.

## Start the backend

```bash
python -m pip install -r backend/requirements.txt
python backend/app.py
```

`frontend/.env.local` is configured with `VITE_API_URL=http://127.0.0.1:5000/api`. The Vite app calls the Flask endpoints at `/api/runs` and `/api/runs/:id/telemetry`; the Flask process reads the checked-in MCAP recordings at startup. Restart Vite after changing the API URL. CORS permits `http://127.0.0.1:5173` and `http://localhost:5173`.

To include a live Jetson session, first make the Jetson's existing read-only `/odom` HTTP endpoint reachable from this computer. If it listens on port 8000 on the Jetson, open an SSH tunnel in another terminal:

```bash
ssh -N -L 8000:127.0.0.1:8000 <user>@<jetson-host>
```

Then start Flask with the tunnel endpoint:

```bash
python backend/app.py --jetson-url http://127.0.0.1:8000
```

The Jetson `/odom` response must be JSON containing an advancing `stamp_ns`, position `x` and `y`, and speed as `speed` or `vx`. Flask polls it, persists snapshots under `recordings/`, and exposes the current session as a `live` run. The frontend polls its telemetry and health status. If your Jetson API is directly reachable over the local network, pass its URL instead of `http://127.0.0.1:8000`. The API is read-only; PWM and IMU are shown for MCAP recordings when those topics exist, while the live `/odom` endpoint supplies speed and position.

The dashboard shows measured wheel speed, raw PWM commands, sensor X-axis acceleration (without gravity compensation), and local GPS odometry positions. Distance integrates absolute wheel speed over its sampled interval. Controller status count and average message rate come from `/mpc/status`; mode, health, target speed, and tracking error remain unavailable because the array fields are undocumented. Missing measurements use null values or empty series, never fabricated zeros. Live Jetson snapshots continue to use the existing SQLite collector; recorded playback needs no database.

## Start the frontend

```bash
cd frontend
npm install
npm run dev
```

## Frontend layout

- `frontend/src/components/` reusable navigation, run selector, stats, charts, GPS, and controller panels
- `frontend/src/pages/Dashboard.jsx` the dashboard page
- `frontend/src/api/api.js` REST API adapter (mock data is used when `VITE_API_URL` is unset)
- `frontend/src/data/mockData.js` generated mock sessions and telemetry

The API exposes `GET /api/runs` and `GET /api/runs/:id/telemetry`. When `VITE_API_URL` is unset, the dashboard uses sample data. When it is set, connection failures are displayed instead of falling back to samples.
