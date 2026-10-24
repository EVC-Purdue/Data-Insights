import { mockRuns, mockTelemetry } from '../data/mockData.js'

const API_URL = import.meta.env.VITE_API_URL?.replace(/\/$/, '')
export const usesMockData = !API_URL

async function getJson(path, signal, options = {}) {
  const response = await fetch(`${API_URL}${path}`, { signal, ...options })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.error || `API request failed with status ${response.status}`)
  }
  return response.json()
}

// With no VITE_API_URL configured, the interface works entirely from local mock data.
export async function getRuns() {
  return API_URL ? getJson('/runs') : mockRuns
}

export async function getRunTelemetry(runId, signal) {
  return API_URL ? getJson(`/runs/${encodeURIComponent(runId)}/telemetry`, signal) : mockTelemetry[runId]
}

export function getHealth(signal) {
  return getJson('/health', signal)
}

export const getSimulatorJobs = (signal) => getJson('/simulator/jobs', signal)
export const getSimulatorEpisodes = (jobId, signal) => getJson(`/simulator/jobs/${encodeURIComponent(jobId)}/episodes`, signal)
export const importSimulatorEpisode = (jobId, episodeId, signal) => getJson('/simulator/import', signal, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jobId, episodeId }),
})
export const getDiagnostics = (runId, signal) => getJson(`/runs/${encodeURIComponent(runId)}/diagnostics`, signal)
export const getRunMeasurements = (runId, signal) => getJson(`/runs/${encodeURIComponent(runId)}/measurements`, signal)
export const analyzeRun = (runId, signal) => getJson(`/runs/${encodeURIComponent(runId)}/analyze`, signal, { method: 'POST' })
