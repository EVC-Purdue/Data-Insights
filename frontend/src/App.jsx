import { useEffect, useState } from 'react'
import { getRuns, usesMockData } from './api/api.js'
import Dashboard from './pages/Dashboard.jsx'
import Sidebar from './components/Sidebar.jsx'
import { mockRuns } from './data/mockData.js'
import SimulatorPicker from './components/SimulatorPicker.jsx'
import DiagnosticsPanel from './components/DiagnosticsPanel.jsx'

export default function App() {
  const [runs, setRuns] = useState(usesMockData ? mockRuns : [])
  const [selectedId, setSelectedId] = useState(usesMockData ? mockRuns[0].id : null)
  const [apiError, setApiError] = useState('')

  useEffect(() => {
    getRuns().then((items) => {
      setRuns(items)
      if (items.length) setSelectedId(items[0].id)
    }).catch((error) => setApiError(error.message))
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
