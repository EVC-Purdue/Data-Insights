# Autonomous Kart Telemetry

The React + Vite dashboard lives in [`frontend/`](frontend/). Its frontend uses local mock telemetry by default and can later switch to a JSON REST API through `VITE_API_URL`.

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

When the backend API is ready, copy `frontend/.env.example` to `frontend/.env.local` and set the API base URL. The adapter expects `GET /runs` to return an array of run summaries and `GET /runs/:id/telemetry` to return that run with `telemetry` series and controller metrics. Adjust only the adapter if the final Flask response contract differs.
