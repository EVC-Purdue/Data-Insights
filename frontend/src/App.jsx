import { useEffect, useState } from 'react'
import { getRuns, usesMockData } from './api/api.js'
import Dashboard from './pages/Dashboard.jsx'
import Sidebar from './components/Sidebar.jsx'
import { mockRuns } from './data/mockData.js'

export default function App() {
  const [runs, setRuns] = useState(mockRuns)
  const [selectedId, setSelectedId] = useState(mockRuns[0].id)
  const [apiError, setApiError] = useState('')

  useEffect(() => {
    getRuns().then((items) => {
      setRuns(items)
      if (items.length) setSelectedId(items[0].id)
    }).catch((error) => setApiError(error.message))
  }, [])

  return <div className="app-shell"><Sidebar usesMockData={usesMockData || Boolean(apiError)} /><main className="main-area"><Dashboard runs={runs} selectedId={selectedId} onRunChange={setSelectedId} apiError={apiError} usesMockData={usesMockData || Boolean(apiError)} /></main></div>
}
