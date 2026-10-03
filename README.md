# Autonomous Kart Telemetry

The React + Vite dashboard lives in [`frontend/`](frontend/). Flask in [`backend/`](backend/) reads MCAP recordings from `src/data` into memory and serves them to the dashboard.

## Start the backend

```bash
python -m pip install -r backend/requirements.txt
python backend/app.py
```

Create `frontend/.env.local` with `VITE_API_URL=http://127.0.0.1:5000/api` before starting Vite. Restart Vite after changing this file. CORS permits `http://127.0.0.1:5173` and `http://localhost:5173`.

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
