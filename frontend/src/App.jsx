import { Component, useEffect, useState } from 'react'
import { getRuns, usesMockData } from './api/api.js'
import Dashboard from './pages/Dashboard.jsx'
import Sidebar from './components/Sidebar.jsx'
import { mockRuns } from './data/mockData.js'
import SimulatorPicker from './components/SimulatorPicker.jsx'
import DiagnosticsPanel from './components/DiagnosticsPanel.jsx'
import SimulatorViewer from './pages/SimulatorViewer.jsx'
import KartRecordingsViewer from './pages/KartRecordingsViewer.jsx'

class DashboardErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) return <main role="alert" style={{ minHeight: '100vh', padding: 32, background: '#101411', color: '#e3e9e3', fontFamily: 'sans-serif' }}>
      <h1>Dashboard could not render</h1>
      <p>{this.state.error.message}</p>
      <pre style={{ whiteSpace: 'pre-wrap', color: '#aab5aa' }}>{this.state.error.stack}</pre>
    </main>
    return this.props.children
  }
}

export default function App() {
  // The primary purpose of this dashboard is browsing physical kart recordings.
  // Keep simulator jobs available as an explicit alternate view.
  const isSimulatorView = new URLSearchParams(window.location.search).get('source') === 'simulator'
  if (!usesMockData) return <DashboardErrorBoundary>{isSimulatorView ? <SimulatorViewer /> : <KartRecordingsViewer />}</DashboardErrorBoundary>
  const [runs, setRuns] = useState(usesMockData ? mockRuns : [])
  const [selectedId, setSelectedId] = useState(usesMockData ? mockRuns[0].id : null)
  const [apiError, setApiError] = useState('')

  useEffect(() => {
    let alive = true
    let retry
    async function loadRuns() {
      try {
        const response = await getRuns()
        if (!alive) return
        const items = response
        setRuns(items)
        if (items.length) setSelectedId(items[0].id)
        setApiError('')
      } catch (error) {
        if (!alive) return
        setApiError(error.message)
        retry = setTimeout(loadRuns, 3000)
      }
    }
    loadRuns()
    return () => { alive = false; clearTimeout(retry) }
  }, [])

  function imported(run) {
    setRuns(items => [...items.filter(item => item.id !== run.id), run])
    setSelectedId(run.id)
    setApiError('')
  }

  return <div className="app-shell"><Sidebar usesMockData={usesMockData || Boolean(apiError)} /><main className="main-area">
    {!usesMockData && <div className="diagnostics-area"><SimulatorPicker onImported={imported} /><DiagnosticsPanel runId={selectedId} /></div>}
    {apiError ? <p className="api-message">Could not load telemetry: {apiError}</p> : <Dashboard runs={runs} selectedId={selectedId} onRunChange={setSelectedId} apiError={apiError} usesMockData={usesMockData || Boolean(apiError)} />}
  </main></div>
}
