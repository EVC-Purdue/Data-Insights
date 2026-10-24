import { useEffect, useRef, useState } from 'react'
import { getSimulatorJobs, getSimulatorEpisodes, importSimulatorEpisode } from '../api/api.js'

export default function SimulatorPicker({ onImported }) {
  const [jobs, setJobs] = useState([])
  const [job, setJob] = useState('')
  const [episodes, setEpisodes] = useState([])
  const [episode, setEpisode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])
  async function perform(action) {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    const timeout = setTimeout(() => controller.abort(), 70000)
    setBusy(true); setError('')
    try { await action(controller.signal) }
    catch (e) { setError(e.name === 'AbortError' ? 'Simulator request timed out or was cancelled.' : e.message) }
    finally { clearTimeout(timeout); setBusy(false) }
  }
  function selectJob(value) {
    setJob(value); setEpisodes([]); setEpisode('')
    if (value) perform(async (signal) => {
      const data = await getSimulatorEpisodes(value, signal)
      setEpisodes(data.episodes)
    })
  }
  return <section className="panel diagnostics-panel" aria-label="Simulator import">
    <h3>Simulator import</h3>
    <div className="diagnostic-controls">
      <button disabled={busy} onClick={() => perform(async (signal) => setJobs(await getSimulatorJobs(signal)))}>Load simulator jobs</button>
      <label>Completed job <select value={job} disabled={busy} onChange={(e) => selectJob(e.target.value)}>
        <option value="">Select job</option>{jobs.filter(j => j.status === 'done').map(j => <option key={j.id} value={j.id}>{j.id}</option>)}
      </select></label>
      <label>Episode <select value={episode} disabled={busy || !job} onChange={(e) => setEpisode(e.target.value)}>
        <option value="">Select episode</option>{episodes.map(e => <option key={e.key} value={e.key}>{e.label} · {e.status || 'completed job'} · {e.key.slice(0, 10)}</option>)}
      </select></label>
      <button disabled={busy || !episode} onClick={() => perform(async (signal) => {
        const run = await importSimulatorEpisode(job, episode, signal)
        onImported(run)
      })}>Import episode</button>
    </div>
    {busy && <p role="status">Loading simulator data…</p>}
    {error && <p role="alert">{error}</p>}
    <p>Imports are cached locally. Reopen cached episodes with the run selector, even offline.</p>
  </section>
}
