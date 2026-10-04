import { useEffect, useState } from 'react'
import { Activity, Gauge, Route, Timer, Zap } from 'lucide-react'
import { getHealth, getRunTelemetry } from '../api/api.js'
import ControllerPanel from '../components/ControllerPanel.jsx'
import GpsMap from '../components/GpsMap.jsx'
import RunSelector from '../components/RunSelector.jsx'
import StatCard from '../components/StatCard.jsx'
import TelemetryChart from '../components/TelemetryChart.jsx'

const timeLabel = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

export default function Dashboard({ runs, selectedId, onRunChange, apiError, usesMockData }) {
  const selectedRun = runs.find((run) => run.id === selectedId) ?? runs[0]
  const [runData, setRunData] = useState(selectedRun)
  const [loading, setLoading] = useState(false)
  const [liveState, setLiveState] = useState(null)
  const isLive = selectedRun?.source === 'live'

  useEffect(() => {
    let current = true
    if (!selectedRun) return
    let timer
    let timeout
    let controller
    setLoading(true)
    setLiveState(null)
    async function refresh() {
      controller = new AbortController()
      // Bound stalled requests so a failed backend cannot freeze polling forever.
      if (isLive) timeout = setTimeout(() => controller.abort(), 5000)
      const [measurement, health] = await Promise.allSettled([
        getRunTelemetry(selectedRun.id, controller.signal),
        ...(isLive ? [getHealth(controller.signal)] : []),
      ])
      clearTimeout(timeout)
      if (!current) return
      if (measurement.status === 'fulfilled' && (!isLive || health.status === 'fulfilled')) {
        setRunData({ ...measurement.value, id: selectedRun.id })
      } else if (!isLive) {
        setRunData(selectedRun)
      }
      if (isLive) {
        const status = health.status === 'rejected' ? 'BACKEND UNREACHABLE'
          : !health.value.connected ? 'JETSON DISCONNECTED'
            : health.value.stale || measurement.status === 'rejected' ? 'STALE DATA' : 'LIVE'
        setLiveState({ id: selectedRun.id, status })
        // Schedule only after both requests settle; batches never overlap.
        timer = setTimeout(refresh, 1000)
      }
      setLoading(false)
    }
    refresh()
    return () => {
      current = false
      clearTimeout(timer)
      clearTimeout(timeout)
      controller?.abort()
    }
  }, [selectedRun?.id, isLive])

  const resolvedRun = runData?.id === selectedRun?.id ? runData : selectedRun
  const telemetry = resolvedRun?.telemetry ?? selectedRun?.telemetry
  const stats = resolvedRun
  const liveStatus = liveState && liveState.id === selectedRun?.id ? liveState.status : 'LOADING'
  const oldMeasurements = isLive && liveStatus !== 'LIVE' && liveStatus !== 'LOADING'
  if (!selectedRun || !telemetry) return <div className="page-content"><p>{isLive ? liveStatus : 'No run telemetry is available.'}</p></div>

  return <div className="page-content">
    <header className="page-header" id="overview"><div><div className="eyebrow"><Activity size={14} />AUTONOMOUS KART <span>/</span> TELEMETRY</div><h1>Run dashboard</h1><p className="page-subtitle">Understand vehicle performance, driver inputs, and controller behavior.</p></div><span className="connection-pill" role="status"><i />{isLive ? liveStatus : loading ? 'LOADING' : 'RUN COMPLETE'}</span></header>
    {oldMeasurements && <p className="api-message" role="status">{liveStatus} — displayed measurements are old; waiting for fresh telemetry.</p>}
    <div className="run-bar"><RunSelector runs={runs} selectedId={selectedRun.id} onChange={onRunChange} /><div className="run-data-note"><span className="data-pulse" />{usesMockData ? 'Sample telemetry' : 'Recorded telemetry'}<small>·</small>{stats.duration.toFixed(1)} sec</div></div>
    <section className="stats-grid" aria-label="Run summary statistics">
      <StatCard label="Current speed" value={stats.currentSpeed?.toFixed(1) ?? 'Unavailable'} unit="m/s" detail="Latest recorded sample" icon={Gauge} tone="green" />
      <StatCard label="Max speed" value={stats.maxSpeed?.toFixed(1) ?? 'Unavailable'} unit="m/s" detail="Peak in this run" icon={Zap} tone="blue" />
      <StatCard label="Distance" value={stats.distance?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? 'Unavailable'} unit="m" detail="Integrated absolute wheel speed" icon={Route} tone="purple" />
      <StatCard label="Run duration" value={timeLabel(stats.duration)} unit="" detail="Recorded telemetry window" icon={Timer} tone="amber" />
    </section>
    {apiError && <p className="api-message">Could not reach the configured API, showing the local mock run.</p>}
    <section className="signals-section" id="signals"><div className="section-heading"><div><h2>Telemetry signals</h2><p>Time-aligned vehicle data from the selected run</p></div><span className="sample-rate">{usesMockData ? 'MOCK DATA · 1 SEC SAMPLES' : 'REST API DATA'}</span></div>
      <div className="charts-grid">
        <TelemetryChart title="Speed" subtitle="Kart speed · /e_comms/kart_speed_m_per_s" data={telemetry.speed} distance={stats.distance} showAxisSelector unit=" m/s" domain={[0, 'auto']} lines={[{ key: 'value', name: 'Speed', color: '#a5ed68' }]} className="wide-chart" />
        <TelemetryChart title="Throttle" subtitle="Throttle command · /e_comms/throttle_pwm" data={telemetry.throttle} distance={stats.distance} showAxisSelector unit={usesMockData ? '%' : ' raw PWM'} domain={['auto', 'auto']} lines={[{ key: 'value', name: 'Throttle', color: '#72b9fa' }]} />
        <TelemetryChart title="Steering" subtitle="Steering input · /e_comms/steering_pwm" data={telemetry.steering} distance={stats.distance} showAxisSelector unit={usesMockData ? '%' : ' raw PWM'} domain={['auto', 'auto']} zero lines={[{ key: 'value', name: 'Steering', color: '#c9a1ff' }]} />
        <TelemetryChart title="IMU / acceleration" subtitle="Sensor X-axis acceleration · /imu" data={telemetry.acceleration} distance={stats.distance} showAxisSelector unit=" m/s²" domain={['auto', 'auto']} zero lines={[{ key: 'value', name: 'Acceleration', color: '#ffc46b' }]} />
      </div>
    </section>
    <div className="bottom-grid"><GpsMap points={telemetry.gps} usesMockData={usesMockData} /><ControllerPanel controller={stats.controller} data={telemetry.commanded} measuredData={telemetry.speed} /></div>
    <footer className="data-footnote"><span>{usesMockData ? 'LOCAL MOCK DATA' : 'REST API DATA'}</span><span>{usesMockData ? 'Set VITE_API_URL to connect your JSON endpoints.' : 'Data loaded through the API adapter.'}</span></footer>
  </div>
}
