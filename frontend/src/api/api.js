import { mockRuns, mockTelemetry } from '../data/mockData.js'

const API_URL = import.meta.env.VITE_API_URL?.replace(/\/$/, '')
export const usesMockData = !API_URL

async function getJson(path) {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`API request failed with status ${response.status}`)
  return response.json()
}

// With no VITE_API_URL configured, the interface works entirely from local mock data.
export async function getRuns() {
  return API_URL ? getJson('/runs') : mockRuns
}

export async function getRunTelemetry(runId) {
  return API_URL ? getJson(`/runs/${encodeURIComponent(runId)}/telemetry`) : mockTelemetry[runId]
}
