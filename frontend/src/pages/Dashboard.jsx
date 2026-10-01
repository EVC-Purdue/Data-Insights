import { useEffect, useState } from 'react'
import { Activity, Gauge, Route, Timer, Zap } from 'lucide-react'
import { getRunTelemetry } from '../api/api.js'
import ControllerPanel from '../components/ControllerPanel.jsx'
import GpsMap from '../components/GpsMap.jsx'
import RunSelector from '../components/RunSelector.jsx'
import StatCard from '../components/StatCard.jsx'
import TelemetryChart from '../components/TelemetryChart.jsx'

const timeLabel = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(5, '0')}`

export default function Dashboard({ runs, selectedId, onRunChange, apiError, usesMockData }) {
  const selectedRun = runs.find((run) => run.id === selectedId) ?? runs[0]
  const [runData, setRunData] = useState(selectedRun)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let current = true
    setLoading(true)
    getRunTelemetry(selectedRun.id).then((data) => {
      if (current) setRunData({ ...data, id: data.id ?? selectedRun.id })
    }).catch(() => {
      if (current) setRunData(selectedRun)
    }).finally(() => {
      if (current) setLoading(false)
    })
    return () => { current = false }
  }, [selectedRun])

  const resolvedRun = runData?.id === selectedRun.id ? runData : selectedRun
  const telemetry = resolvedRun?.telemetry ?? selectedRun.telemetry
  const stats = resolvedRun
  if (!selectedRun || !telemetry) return <div className="page-content"><p>No run telemetry is available.</p></div>

  return <div className="page-content">
    <header className="page-header" id="overview"><div><div className="eyebrow"><Activity size={14} />AUTONOMOUS KART <span>/</span> TELEMETRY</div><h1>Run dashboard</h1><p className="page-subtitle">Understand vehicle performance, driver inputs, and controller behavior.</p></div><span className="connection-pill"><i />{loading ? 'LOADING' : 'RUN COMPLETE'}</span></header>
    <div className="run-bar"><RunSelector runs={runs} selectedId={selectedRun.id} onChange={onRunChange} /><div className="run-data-note"><span className="data-pulse" />{apiError ? 'Using local mock data' : 'Sample telemetry'}<small>·</small>{stats.duration.toFixed(1)} sec</div></div>
    <section className="stats-grid" aria-label="Run summary statistics">
      <StatCard label="Current speed" value={stats.currentSpeed.toFixed(1)} unit="m/s" detail="Latest recorded sample" icon={Gauge} tone="green" />
      <StatCard label="Max speed" value={stats.maxSpeed.toFixed(1)} unit="m/s" detail="Peak in this run" icon={Zap} tone="blue" />
      <StatCard label="Distance" value={stats.distance.toLocaleString()} unit="m" detail="Estimated run distance" icon={Route} tone="purple" />
      <StatCard label="Run duration" value={timeLabel(stats.duration)} unit="" detail="Recorded telemetry window" icon={Timer} tone="amber" />
    </section>
    {apiError && <p className="api-message">Could not reach the configured API, showing the local mock run.</p>}
    <section className="signals-section" id="signals"><div className="section-heading"><div><h2>Telemetry signals</h2><p>Time-aligned vehicle data from the selected run</p></div><span className="sample-rate">{usesMockData ? 'MOCK DATA · 1 SEC SAMPLES' : 'REST API DATA'}</span></div>
      <div className="charts-grid">
        <TelemetryChart title="Speed vs. time" subtitle="Kart speed · /e_comms/kart_speed_m_per_s" data={telemetry.speed} unit=" m/s" domain={[0, 'auto']} lines={[{ key: 'value', name: 'Speed', color: '#a5ed68' }]} className="wide-chart" />
        <TelemetryChart title="Throttle vs. time" subtitle="Throttle command · /e_comms/throttle_pwm" data={telemetry.throttle} unit="%" domain={[0, 100]} lines={[{ key: 'value', name: 'Throttle', color: '#72b9fa' }]} />
        <TelemetryChart title="Steering vs. time" subtitle="Steering input · /e_comms/steering_pwm" data={telemetry.steering} unit="%" domain={[-100, 100]} zero lines={[{ key: 'value', name: 'Steering', color: '#c9a1ff' }]} />
        <TelemetryChart title="IMU / acceleration" subtitle="Longitudinal acceleration · /imu" data={telemetry.acceleration} unit=" m/s²" domain={[-4, 4]} zero lines={[{ key: 'value', name: 'Acceleration', color: '#ffc46b' }]} />
      </div>
    </section>
    <div className="bottom-grid"><GpsMap points={telemetry.gps} /><ControllerPanel controller={stats.controller} data={telemetry.commanded} /></div>
    <footer className="data-footnote"><span>{usesMockData ? 'LOCAL MOCK DATA' : 'REST API DATA'}</span><span>{usesMockData ? 'Set VITE_API_URL to connect your JSON endpoints.' : 'Data loaded through the API adapter.'}</span></footer>
  </div>
}
