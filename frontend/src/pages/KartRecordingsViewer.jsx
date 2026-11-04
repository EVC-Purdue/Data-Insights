import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, ChevronDown, CircleHelp, MapPin, Pause, Play, Search, Scan, ZoomIn, ZoomOut } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getRuns, getRunTelemetry } from '../api/api.js'
import DiagnosticsPanel from '../components/DiagnosticsPanel.jsx'

const asText = value => value == null ? '' : String(value)
const valueText = (value, digits = 1) => Number.isFinite(value) ? Number(value).toFixed(digits) : '—'
const series = (run, key) => run?.telemetry?.[key] || []
const displayPoints = (points, limit = 2400) => points.length <= limit ? points : points.filter((_, i) => i % Math.ceil(points.length / limit) === 0)
const dateLabel = value => value ? new Date(value).toLocaleString() : 'Date unavailable'
const closest = (points, time) => points.length ? points.reduce((best, point) => Math.abs(point.time - time) < Math.abs(best.time - time) ? point : best, points[0]) : null
const headingDegrees = point => point && Number.isFinite(point.value) ? (point.value * 180 / Math.PI + 360) % 360 : null
const compassDirection = degrees => degrees == null ? '—' : ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round((((90 - degrees) % 360) + 360) % 360 / 45) % 8]

function Stat({ title, value, unit, help }) {
  return <div className="sim-metric" title={help}><span>{title}<i aria-hidden="true">i</i></span><strong>{value}<small>{unit}</small></strong></div>
}

function RealSignalChart({ title, unit, points, color, time, range, onHover }) {
  const data = useMemo(() => displayPoints(points).map(point => ({ time: point.time, value: point.value })), [points])
  const focus = closest(points, time)
  return <section className="sim-chart">
    <header><strong>{title}</strong><span>{unit}</span></header>
    {data.length ? <div className="sim-chart-plot"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} onMouseMove={state => {
      const pointTime = state?.activePayload?.[0]?.payload?.time
      if (Number.isFinite(pointTime)) onHover(pointTime)
    }} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
      <CartesianGrid stroke="#45546a" vertical={false} strokeDasharray="3 5" />
      <XAxis dataKey="time" type="number" domain={range || ['dataMin', 'dataMax']} tickLine={false} axisLine={false} tick={{ fill: '#c2cedd', fontSize: 10 }} tickFormatter={v => `${Number(v).toFixed(2)}s`} />
      <YAxis width={46} tickLine={false} axisLine={false} tick={{ fill: '#c2cedd', fontSize: 10 }} />
      <Tooltip contentStyle={{ background: '#192332', border: '1px solid #53647a', borderRadius: 5, fontSize: 11 }} labelFormatter={v => `${Number(v).toFixed(2)} s`} />
      {focus && <><ReferenceLine x={focus.time} stroke="#e5edf5" strokeDasharray="3 3" strokeOpacity={0.75} /><ReferenceDot x={focus.time} y={focus.value} r={4} fill={color} stroke="#f4f7fb" strokeWidth={1.5} isFront /></>}
      <Line dataKey="value" name={title} stroke={color} dot={false} strokeWidth={2.3} isAnimationActive={false} connectNulls={false} />
    </LineChart></ResponsiveContainer></div> : <div className="sim-chart-empty">No signal recorded in this bag</div>}
    {data.length > 0 && <div className="sim-chart-readout" aria-live="polite"><span><i style={{ background: color }}/>CURRENT SAMPLE</span><strong>{valueText(focus?.value, 2)} <small>{unit}</small></strong><em>{focus ? `${focus.time.toFixed(2)} s` : 'No sample'}</em></div>}
  </section>
}

const mpcCostFields = [
  ['Lateral offset', 'lateral_offset'], ['Heading', 'heading'], ['Speed', 'speed'],
  ['Steering', 'steering'], ['Steering rate', 'steering_rate'], ['Acceleration', 'acceleration'],
  ['Boundary', 'boundary'], ['Progress', 'progress'], ['Terminal lateral offset', 'terminal_lateral_offset'],
  ['Terminal heading', 'terminal_heading'], ['Lateral acceleration', 'lateral_acceleration'], ['Edge', 'edge'],
]

function MpcCostPanel({ points, breakdown, time, range, onHover }) {
  const chartData = useMemo(() => displayPoints(points).map(point => ({ time: point.time, value: point.value })), [points])
  const focus = closest(points, time)
  const terms = closest(breakdown, time)
  const maxMagnitude = Math.max(1, ...mpcCostFields.map(([, key]) => Math.abs(terms?.[key] ?? 0)))
  return <section className="sim-cost-panel">
    <header className="sim-cost-heading"><div><strong>MPC objective cost</strong><span>Recorded from /mpc/status · objective units depend on planner weights</span></div>
      <b>{focus ? valueText(focus.value, 2) : '—'}<small>{focus ? ` at ${focus.time.toFixed(2)} s` : ''}</small></b>
    </header>
    {chartData.length ? <div className="sim-cost-layout">
      <div className="sim-cost-plot"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} onMouseMove={state => {
        const pointTime = state?.activePayload?.[0]?.payload?.time
        if (Number.isFinite(pointTime)) onHover(pointTime)
      }} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="#45546a" vertical={false} strokeDasharray="3 5" />
        <XAxis dataKey="time" type="number" domain={range || ['dataMin', 'dataMax']} tickLine={false} axisLine={false} tick={{ fill: '#c2cedd', fontSize: 10 }} tickFormatter={v => `${Number(v).toFixed(1)}s`} />
        <YAxis width={56} tickLine={false} axisLine={false} tick={{ fill: '#c2cedd', fontSize: 10 }} tickFormatter={v => Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })} />
        <Tooltip contentStyle={{ background: '#192332', border: '1px solid #53647a', borderRadius: 5, fontSize: 11 }} labelFormatter={v => `${Number(v).toFixed(2)} s`} formatter={v => [valueText(v, 2), 'Total objective']} />
        {focus && <><ReferenceLine x={focus.time} stroke="#e5edf5" strokeDasharray="3 3" strokeOpacity={0.75} /><ReferenceDot x={focus.time} y={focus.value} r={4} fill="#f1b85b" stroke="#f4f7fb" strokeWidth={1.5} isFront /></>}
        <Line dataKey="value" name="Total objective" stroke="#f1b85b" dot={false} strokeWidth={2.2} isAnimationActive={false} connectNulls={false} />
      </LineChart></ResponsiveContainer></div>
      <div className="sim-cost-terms"><div className="sim-cost-terms-title"><strong>Cost breakdown</strong><span>{terms ? `sample ${terms.time.toFixed(2)} s` : 'No sample'}</span></div>
        {mpcCostFields.map(([label, key]) => {
          const value = terms?.[key]
          const magnitude = Number.isFinite(value) ? Math.abs(value) / maxMagnitude * 50 : 0
          return <div className="sim-cost-term" key={key}>
            <span>{label}</span><b>{valueText(value, 2)}</b>
            <div className="sim-cost-bar"><i className={value < 0 ? 'negative' : ''} style={{ left: value < 0 ? `${50 - magnitude}%` : '50%', width: `${magnitude}%` }} /></div>
          </div>
        })}
      </div>
    </div> : <div className="sim-cost-empty">This bag has no decodable MPC cost samples.</div>}
  </section>
}

function SelectedPointData({ run, time }) {
  const gps = series(run, 'gps').filter(point => Number.isFinite(point.x) && Number.isFinite(point.y))
  const current = closest(gps, time)
  const currentIndex = current ? gps.indexOf(current) : -1
  const before = gps[Math.max(0, currentIndex - 1)], after = gps[Math.min(gps.length - 1, currentIndex + 1)]
  const dx = before && after ? after.x - before.x : 0, dy = before && after ? after.y - before.y : 0
  const course = before && after && Math.hypot(dx, dy) > 1e-6 ? { time: current.time, value: Math.atan2(dy, dx) } : null
  const gpsTime = current?.time ?? time
  const heading = closest(series(run, 'heading'), gpsTime)
  const pointSignals = [
    ['Wheel speed', 'speed', 'm/s'], ['Throttle', 'throttle', 'PWM'], ['Steering', 'steering', 'PWM'],
    ['IMU X acceleration', 'acceleration', 'm/s²'], ['Odom heading', 'heading', 'deg'], ['GPS course', 'course', 'deg'], ['Commanded speed', 'commanded', 'm/s'],
  ].map(([label, key, unit]) => {
    const point = key === 'course' ? course : closest(series(run, key), gpsTime)
    const value = key === 'heading' || key === 'course' ? headingDegrees(point) : point?.value
    const display = key === 'commanded' && point
      ? `target ${valueText(point.target, 2)} / actual ${valueText(point.actual, 2)}`
      : `${valueText(value, key === 'heading' || key === 'course' ? 1 : 3)} ${unit}`
    return { label, display, sampleTime: point?.time }
  })

  return <section className="sim-point-data" aria-live="polite">
    <header><strong>Selected trajectory point</strong><span>{current ? `${gpsTime.toFixed(2)} s` : 'No GPS point'}</span></header>
    {current ? <><div className="sim-point-gps"><span>GPS X <b>{valueText(current.x, 3)} m</b></span><span>GPS Y <b>{valueText(current.y, 3)} m</b></span></div><div className="sim-point-grid">{pointSignals.map(item => <div key={item.label}><span>{item.label}</span><strong>{item.display}</strong>{item.sampleTime != null ? <small>sample Δt {Math.abs(item.sampleTime - gpsTime).toFixed(3)} s</small> : <small>No sample recorded</small>}</div>)}</div></> : <p>No GPS trajectory point is available for this run.</p>}
  </section>
}

function RealTrack({ run, time, setTime, playing, setPlaying }) {
  const [dragMode, setDragMode] = useState(null)
  const dragOrigin = useRef(null)
  const suppressClick = useRef(false)
  const [trackView, setTrackView] = useState({ zoom: 1, x: 50, y: 50 })
  const gps = series(run, 'gps').filter(p => Number.isFinite(p.x) && Number.isFinite(p.y))
  const bounds = gps.reduce((b, p) => ({ minX: Math.min(b.minX, p.x), maxX: Math.max(b.maxX, p.x), minY: Math.min(b.minY, p.y), maxY: Math.max(b.maxY, p.y) }), { minX: 0, maxX: 1, minY: 0, maxY: 1 })
  const span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, 1)
  const xy = p => [8 + (p.x - bounds.minX) / span * 84, 92 - (p.y - bounds.minY) / span * 84]
  const coordinates = gps.map(xy)
  const isClosed = coordinates.length > 3 && Math.hypot(coordinates[0][0] - coordinates.at(-1)[0], coordinates[0][1] - coordinates.at(-1)[1]) < 7
  const centerline = coordinates.map((_, index) => {
    let x = 0, y = 0, count = 0
    for (let offset = -6; offset <= 6; offset += 1) {
      let neighbor = index + offset
      if (isClosed) neighbor = (neighbor + coordinates.length) % coordinates.length
      if (neighbor < 0 || neighbor >= coordinates.length) continue
      x += coordinates[neighbor][0]; y += coordinates[neighbor][1]; count += 1
    }
    return [x / count, y / count]
  })
  const makePath = points => points.map((point, index) => `${index ? 'L' : 'M'}${point.join(',')}`).join(' ')
  const path = makePath(coordinates)
  const centerlinePath = makePath(centerline)
  const current = closest(gps, time)
  const currentIndex = current ? gps.indexOf(current) : -1
  const lookaheadEnd = currentIndex < 0 ? -1 : gps.findIndex((point, index) => index >= currentIndex && point.time >= current.time + 4)
  const previewEnd = lookaheadEnd < 0 ? gps.length - 1 : lookaheadEnd
  const routePreview = currentIndex >= 0 ? makePath(centerline.slice(currentIndex, previewEnd + 1)) : ''
  const headings = series(run, 'heading')
  const heading = closest(headings, time)
  const before = gps[Math.max(0, currentIndex - 1)], after = gps[Math.min(gps.length - 1, currentIndex + 1)]
  const courseDx = before && after ? after.x - before.x : 0, courseDy = before && after ? after.y - before.y : 0
  const course = before && after && Math.hypot(courseDx, courseDy) > 1e-6 ? { time: current.time, value: Math.atan2(courseDy, courseDx) } : null
  const degrees = headingDegrees(heading) ?? headingDegrees(course)
  const headingSource = heading ? 'ODOM YAW' : course ? 'GPS COURSE' : 'NO HEADING DATA'
  const times = gps.length ? gps : series(run, 'speed')
  const start = times[0]?.time ?? 0, end = times.at(-1)?.time ?? run?.duration ?? 0
  const viewSize = 100 / trackView.zoom
  const viewX = trackView.x - viewSize / 2, viewY = trackView.y - viewSize / 2
  const trackViewBox = `${viewX} ${viewY} ${viewSize} ${viewSize}`
  const closeCenter = current ? xy(current) : centerline[0] || [50, 50]
  const closeSize = 20
  const closeViewBox = `${closeCenter[0] - closeSize / 2} ${closeCenter[1] - closeSize / 2} ${closeSize} ${closeSize}`
  useEffect(() => setTrackView({ zoom: 1, x: 50, y: 50 }), [run?.id])
  function svgCoordinates(event) {
    const rect = event.currentTarget.getBoundingClientRect()
    const scale = Math.min(rect.width / viewSize, rect.height / viewSize)
    const offsetX = (rect.width - scale * viewSize) / 2, offsetY = (rect.height - scale * viewSize) / 2
    return [viewX + (event.clientX - rect.left - offsetX) / scale, viewY + (event.clientY - rect.top - offsetY) / scale]
  }
  function zoomTrack(factor, center = current ? xy(current) : [50, 50]) {
    setTrackView(previous => {
      const zoom = Math.max(1, Math.min(50, previous.zoom * factor))
      return { zoom, x: center[0], y: center[1] }
    })
  }
  function wheelTrack(event) {
    event.preventDefault()
    const [x, y] = svgCoordinates(event)
    setTrackView(previous => {
      const zoom = Math.max(1, Math.min(50, previous.zoom * (event.deltaY < 0 ? 1.2 : 1 / 1.2)))
      if (zoom === 1) return { zoom: 1, x: 50, y: 50 }
      const oldSize = 100 / previous.zoom, newSize = 100 / zoom
      const fractionX = (x - (previous.x - oldSize / 2)) / oldSize
      const fractionY = (y - (previous.y - oldSize / 2)) / oldSize
      return { zoom, x: x + (0.5 - fractionX) * newSize, y: y + (0.5 - fractionY) * newSize }
    })
  }
  function selectTrackPoint(event) {
    if (!gps.length) return
    const [x, y] = svgCoordinates(event)
    const nearest = gps.reduce((best, point) => {
      const [px, py] = xy(point), [bx, by] = xy(best)
      return (px - x) ** 2 + (py - y) ** 2 < (bx - x) ** 2 + (by - y) ** 2 ? point : best
    }, gps[0])
    setPlaying(false)
    setTime(nearest.time)
  }
  function startTrackDrag(event) {
    if (!gps.length || event.button !== 0) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    const mode = event.target.closest?.('[data-kart-marker]') ? 'kart' : 'map'
    dragOrigin.current = { mode, clientX: event.clientX, clientY: event.clientY, x: trackView.x, y: trackView.y, moved: false }
    setDragMode(mode)
    if (mode === 'kart') selectTrackPoint(event)
  }
  function moveTrackDrag(event) {
    const origin = dragOrigin.current
    if (!origin) return
    const dx = event.clientX - origin.clientX, dy = event.clientY - origin.clientY
    if (!origin.moved && Math.hypot(dx, dy) > 2) origin.moved = true
    if (origin.mode === 'kart') {
      selectTrackPoint(event)
    } else if (origin.moved) {
      const rect = event.currentTarget.getBoundingClientRect()
      const viewSize = 100 / trackView.zoom
      setTrackView(previous => ({ ...previous, x: origin.x - dx * viewSize / rect.width, y: origin.y - dy * viewSize / rect.height }))
    }
  }
  function endTrackDrag(event) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (dragOrigin.current?.moved) suppressClick.current = true
    dragOrigin.current = null
    setDragMode(null)
  }
  function clickTrack(event) {
    if (suppressClick.current) {
      suppressClick.current = false
      return
    }
    selectTrackPoint(event)
  }
  useEffect(() => {
    if (!playing || !run) return
    const timer = setInterval(() => setTime(t => { if (t >= end) { setPlaying(false); return start } return t + 0.08 }), 40)
    return () => clearInterval(timer)
  }, [playing, run?.id, end, start, setPlaying])

  return <div className="sim-track-column">
    <section className="sim-track">
      <div className="sim-track-toolbar"><div className="sim-control-group"><button aria-label={playing ? 'Pause playback' : 'Play playback'} onClick={() => setPlaying(v => !v)}>{playing ? <Pause size={14}/> : <Play size={14}/>}</button><span>{playing ? 'Playing' : 'Paused'}</span></div><span>RECORDED KART TRAJECTORY</span><div className="sim-zoom-controls"><button aria-label="Zoom out on trajectory" onClick={() => zoomTrack(1 / 1.5)} disabled={trackView.zoom <= 1}><ZoomOut size={13}/></button><span>{trackView.zoom.toFixed(1)}×</span><button aria-label="Zoom in on trajectory" onClick={() => zoomTrack(1.5)} disabled={trackView.zoom >= 50}><ZoomIn size={13}/></button><button aria-label="Fit full trajectory" onClick={() => setTrackView({ zoom: 1, x: 50, y: 50 })}><Scan size={13}/></button></div></div>
      {path ? <svg viewBox={trackViewBox} className={`sim-track-svg${dragMode ? ' is-dragging' : ''}${dragMode === 'kart' ? ' is-dragging-kart' : ''}`} role="img" aria-label="GPS-derived track estimate with smoothed centerline and recorded route preview; drag the map to pan or drag the kart marker to move it along the path, use the wheel to zoom" onClick={clickTrack} onWheel={wheelTrack} onPointerDown={startTrackDrag} onPointerMove={moveTrackDrag} onPointerUp={endTrackDrag} onPointerCancel={endTrackDrag}>
        <rect x={viewX} y={viewY} width={viewSize} height={viewSize} fill="transparent" pointerEvents="all"/>
        <path d={centerlinePath} fill="none" stroke="#98a2b0" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" opacity="0.72"/>
        <path d={centerlinePath} fill="none" stroke="#253247" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"/>
        <path d={path} fill="none" stroke="#59b7d8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" vectorEffect="non-scaling-stroke"/>
        {routePreview && <path d={routePreview} fill="none" stroke="#f1b85b" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>}
        <path d={centerlinePath} fill="none" stroke="#e1e6ee" strokeWidth="1.3" strokeDasharray="5 5" strokeLinecap="round" opacity="0.95" vectorEffect="non-scaling-stroke"/>
        <circle cx={xy(gps[0])[0]} cy={xy(gps[0])[1]} r="2.5" fill="#4adea5" vectorEffect="non-scaling-stroke"><title>Start of recorded GPS route</title></circle>
        {current && <g data-kart-marker="" transform={`translate(${xy(current)[0]} ${xy(current)[1]}) scale(${1 / trackView.zoom})`}><circle r="4.5" fill="#192332" stroke="#f1b85b" strokeWidth="1.4" vectorEffect="non-scaling-stroke"/><path d="M0 -7 L3.5 2.5 L0 1 L-3.5 2.5 Z" fill="#f1b85b" transform={`rotate(${90 - (degrees ?? 0)})`} vectorEffect="non-scaling-stroke"/></g>}
      </svg> : <div className="sim-empty"><MapPin size={20}/>No GPS positions were recorded in this run</div>}
      <div className="sim-track-caption"><span><i className="sim-dot start"/>RUN START</span><span><i className="sim-dot current"/>KART</span><span><i className="sim-dot centerline-dot"/>CENTERLINE</span><span><i className="sim-dot route-dot"/>RECORDED 4 s AHEAD</span><span>{time.toFixed(2)} s</span></div>
      <input aria-label="Playback time" className="sim-timeline" type="range" min={start} max={Math.max(end, start + 0.01)} step="0.05" value={Math.min(time, Math.max(end, start + 0.01))} onChange={e => setTime(Number(e.target.value))}/>
    </section>
    <section className="sim-kart-view" aria-label="Kart close-up viewer">
      <header><strong>Kart close-up</strong><span>{degrees == null ? 'HEADING UNAVAILABLE' : `${degrees.toFixed(1)}° · ${compassDirection(degrees)}`}</span></header>
      {current ? <svg viewBox={closeViewBox} role="img" aria-label={`Top-down kart view, heading ${degrees == null ? 'unavailable' : `${degrees.toFixed(0)} degrees ${compassDirection(degrees)}`}`}>
        <path d={centerlinePath} fill="none" stroke="#969eaa" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" opacity="0.72"/>
        <path d={centerlinePath} fill="none" stroke="#253247" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"/>
        <path d={path} fill="none" stroke="#d7b977" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>
        <path d={centerlinePath} fill="none" stroke="#f1f5f9" strokeWidth="1.5" strokeDasharray="5 5" opacity="0.98" vectorEffect="non-scaling-stroke"/>
        <g transform={`translate(${closeCenter[0]} ${closeCenter[1]}) rotate(${90 - (degrees ?? 0)}) scale(${0.15 * closeSize / 30})`}>
          <rect x="-4.2" y="-3.8" width="2" height="3.2" rx=".4" fill="#080c12"/><rect x="2.2" y="-3.8" width="2" height="3.2" rx=".4" fill="#080c12"/>
          <rect x="-4.2" y="2" width="2" height="3.2" rx=".4" fill="#080c12"/><rect x="2.2" y="2" width="2" height="3.2" rx=".4" fill="#080c12"/>
          <path d="M0 -6.5 C2.2 -5.4 2.6 -3.8 2.4 -1.8 L2.1 4.8 Q0 6.2 -2.1 4.8 L-2.4 -1.8 C-2.6 -3.8 -2.2 -5.4 0 -6.5Z" fill="#cbb68e" stroke="#f1b85b" strokeWidth=".45"/>
          <path d="M0 -5.1 L1 -2.6 L0 -3.1 L-1 -2.6Z" fill="#f1b85b"/>
        </g>
      </svg> : <div className="sim-kart-view-empty">No GPS position for this run</div>}
      <small>Top-down view · follows the selected time</small>
    </section>
    <section className="sim-heading-card">
      <div className="sim-heading-compass"><svg viewBox="0 0 100 100" role="img" aria-label={degrees == null ? 'Heading unavailable' : `Kart heading ${degrees.toFixed(0)} degrees ${compassDirection(degrees)}`}>
        <circle cx="50" cy="50" r="43" fill="none" stroke="#354154" strokeWidth="1.5"/><circle cx="50" cy="50" r="31" fill="#151d2a" stroke="#2b394c"/>
        <text x="50" y="13" textAnchor="middle">+Y</text><text x="88" y="53" textAnchor="middle">+X</text>
        {degrees != null && <g transform={`rotate(${90 - degrees} 50 50)`}><path d="M50 20 L61 55 L50 49 L39 55 Z" fill="#60b8d5"/><circle cx="50" cy="50" r="4" fill="#f1b85b"/></g>}
      </svg></div>
      <div className="sim-heading-values"><span>{headingSource}</span><strong>{degrees == null ? '—' : `${degrees.toFixed(1)}°`}</strong><b>{compassDirection(degrees)}</b><small>{heading ? 'ROS yaw from map +X; arrow shows kart orientation.' : course ? 'Direction of travel inferred from consecutive GPS points.' : 'No orientation or GPS course available for this point.'}</small></div>
    </section>
  </div>
}

export default function KartRecordingsViewer() {
  const [runs, setRuns] = useState([]), [runId, setRunId] = useState(new URLSearchParams(location.search).get('run') || '')
  const [run, setRun] = useState(null), [query, setQuery] = useState(''), [day, setDay] = useState('all')
  const [busy, setBusy] = useState(true), [error, setError] = useState(''), [time, setTime] = useState(0), [playing, setPlaying] = useState(false)
  const [fitToScreen, setFitToScreen] = useState(false)
  const [chartRange, setChartRange] = useState(null)

  useEffect(() => {
    let alive = true, retry
    const load = async () => {
      try {
        const all = await getRuns()
        if (!alive) return
        const realRuns = all.filter(item => item.source === 'recording')
        setRuns(realRuns)
        setRunId(current => current && realRuns.some(item => item.id === current) ? current : realRuns[0]?.id || '')
        setError(realRuns.length ? '' : 'No real-kart recordings were loaded by Flask yet.')
        setBusy(false)
      } catch (e) {
        if (!alive) return
        setError(e.message); retry = setTimeout(load, 3000)
      }
    }
    load()
    return () => { alive = false; clearTimeout(retry) }
  }, [])

  useEffect(() => {
    if (!runId) return
    setChartRange(null)
    let alive = true
    setBusy(true); setRun(null); setError('')
    getRunTelemetry(runId).then(value => { if (alive) { setRun(value); setTime(0) } }).catch(e => { if (alive) setError(e.message) }).finally(() => { if (alive) setBusy(false) })
    const url = new URL(location.href); url.searchParams.set('run', runId); history.replaceState({}, '', url)
    return () => { alive = false }
  }, [runId])

  const days = useMemo(() => [...new Set(runs.map(item => item.date?.slice(0, 10)).filter(Boolean))].sort().reverse(), [runs])
  const visibleRuns = runs.filter(item => (day === 'all' || item.date?.startsWith(day)) && `${item.name} ${item.id}`.toLowerCase().includes(query.toLowerCase()))
  const selected = runs.find(item => item.id === runId)
  const speed = series(run, 'speed'), throttle = series(run, 'throttle'), steering = series(run, 'steering'), accel = series(run, 'acceleration'), gps = series(run, 'gps')
  const headingChart = useMemo(() => {
    const recorded = series(run, 'heading')
    if (recorded.length) return recorded.map(p => ({ ...p, value: headingDegrees(p) }))
    return gps.flatMap((point, index) => {
      const before = gps[Math.max(0, index - 1)], after = gps[Math.min(gps.length - 1, index + 1)]
      return before && after && Math.hypot(after.x - before.x, after.y - before.y) > 1e-6
        ? [{ time: point.time, value: (Math.atan2(after.y - before.y, after.x - before.x) * 180 / Math.PI + 360) % 360 }]
        : []
    })
  }, [run, gps])
  const fullChartRange = useMemo(() => {
    const times = [speed, throttle, steering, accel, headingChart, series(run, 'mpcCost')].flatMap(points => points.map(point => point.time)).filter(Number.isFinite)
    if (!times.length) return [0, Math.max(run?.duration || 0, 1)]
    const min = Math.min(...times), max = Math.max(...times)
    return [min, max > min ? max : min + 1]
  }, [speed, throttle, steering, accel, headingChart, run?.duration, run])
  const visibleChartRange = chartRange || fullChartRange
  const peakAccel = accel.reduce((max, p) => Number.isFinite(p.value) ? Math.max(max, Math.abs(p.value)) : max, 0)
  const bagFolder = selected?.name || run?.name || ''
  const sourceHref = bagFolder ? `https://github.com/EVC-Purdue/AutonomousKart/tree/main/bags/${encodeURIComponent(bagFolder)}` : 'https://github.com/EVC-Purdue/AutonomousKart/tree/main/bags'

  function choose(item) { setPlaying(false); setRunId(item.id) }
  function zoomCharts(factor) {
    const [fullStart, fullEnd] = fullChartRange
    const [currentStart, currentEnd] = visibleChartRange
    const fullSpan = fullEnd - fullStart
    const span = Math.max(fullSpan / 1000000, Math.min(fullSpan, (currentEnd - currentStart) / factor))
    const center = time >= currentStart && time <= currentEnd ? time : (currentStart + currentEnd) / 2
    const start = Math.max(fullStart, Math.min(fullEnd - span, center - span / 2))
    setChartRange([start, start + span])
  }
  function resetChartZoom() { setChartRange(null) }

  return <div className={`sim-app${fitToScreen ? ' sim-fit-view' : ''}`}>
    <aside className="sim-sidebar">
      <a className="sim-brand" href="/"><span className="sim-brand-mark"><Activity size={16}/></span><b>EVC <i>KART</i></b></a>
      <nav><a className="active" href="#recordings">Runs</a><a href="#viewer">Telemetry</a></nav>
      <div className="sim-side-section"><span>REAL KART RUNS</span><label className="sim-search"><Search size={13}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter recordings"/></label>
        <div className="sim-job-list">{visibleRuns.map(item => <button key={item.id} className={runId === item.id ? 'selected' : ''} onClick={() => choose(item)}><strong>{asText(item.name)}</strong><small>{dateLabel(item.date)} · {valueText(item.duration)} s</small></button>)}</div>
      </div>
      <div className="sim-sidebar-foot"><i/>REAL VEHICLE MCAP DATA<small><a href="https://github.com/EVC-Purdue/AutonomousKart/tree/main/bags" target="_blank" rel="noreferrer">AutonomousKart / bags</a></small></div>
    </aside>
    <main className="sim-main">
      <header className="sim-job-head"><div><div className="sim-breadcrumb">KART RUNS <span>/</span> REAL VEHICLE</div><h1>{asText(selected?.name || 'Kart recordings')}</h1><p>{dateLabel(selected?.date)} <span>·</span> Recorded hardware telemetry</p></div><div className="sim-head-actions"><a className="sim-recordings-link" href="?source=simulator">Simulator runs</a><a className="sim-open-source" href={sourceHref} target="_blank" rel="noreferrer">Open bag on GitHub ↗</a></div></header>
      <section className="sim-filterbar"><label><select value={day} onChange={e => setDay(e.target.value)}><option value="all">All dates</option>{days.map(item => <option value={item} key={item}>{item}</option>)}</select><ChevronDown size={12}/></label><label className="real-source-filter">REAL VEHICLE BAGS</label><span className="sim-filter-count">{visibleRuns.length} recordings</span></section>
      <section className="sim-metrics" id="recordings">
        <Stat title="Peak speed" value={valueText(selected?.maxSpeed)} unit="m/s" help="Highest wheel-speed sample recorded in this run."/><Stat title="Distance" value={valueText(selected?.distance)} unit="m" help="Distance estimated by integrating the absolute wheel-speed samples."/><Stat title="Duration" value={valueText(selected?.duration)} unit="s" help="Time span of the recorded bag."/><Stat title="GPS samples" value={gps.length.toLocaleString()} unit="pts" help="Recorded /gps odometry positions."/><Stat title="Peak IMU X" value={valueText(peakAccel)} unit="m/s²" help="Largest absolute X-axis acceleration measurement from the IMU."/><Stat title="Steering samples" value={steering.length.toLocaleString()} unit="pts" help="Recorded steering PWM samples."/><Stat title="MPC status" value={selected?.controller?.frequency ? valueText(selected.controller.frequency) : '—'} unit="Hz" help="Observed /mpc/status message rate; this is not a controller health score."/>
      </section>
      <details className="sim-breakdown"><summary className="sim-section-heading"><div><h2>Run breakdown</h2><p>Select a real kart run to inspect its path and recorded signals.</p></div><span>{busy ? 'LOADING…' : `${visibleRuns.length} SHOWN`} <ChevronDown size={14}/></span></summary>
        <div className="sim-table-wrap"><table><thead><tr><th>Recording</th><th>Date</th><th>Duration</th><th>Peak speed</th><th>Distance</th><th>GPS points</th><th>MPC rate</th><th>Source</th></tr></thead><tbody>{visibleRuns.slice(0, 200).map(item => <tr key={item.id} className={runId === item.id ? 'chosen' : ''} onClick={() => choose(item)}><td><button>{item.name}</button></td><td>{item.date ? new Date(item.date).toLocaleDateString() : '—'}</td><td>{valueText(item.duration)} s</td><td>{valueText(item.maxSpeed)} m/s</td><td>{valueText(item.distance)} m</td><td>{item.sampleCounts?.gps?.toLocaleString() ?? '—'}</td><td>{item.controller?.frequency ? `${valueText(item.controller.frequency)} Hz` : '—'}</td><td><span className="sim-status">REAL BAG</span></td></tr>)}{!visibleRuns.length && <tr><td colSpan="8" className="sim-table-empty">{busy ? 'Waiting for recording index…' : error || 'No runs match this filter.'}</td></tr>}</tbody></table></div>
      </details>
      <section className="sim-viewer" id="viewer"><div className="sim-section-heading"><div><h2>Run viewer</h2><p>{selected ? `${selected.name} · ${selected.id}` : 'Select a recording above'}</p></div><div className="sim-view-actions"><label className="sim-view-select">{selected?.name || 'Select run'}<select aria-label="Select real kart recording" value={runId} onChange={e => setRunId(e.target.value)}><option value="">Select run</option>{runs.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select><ChevronDown size={13}/></label><button className="sim-layout-toggle" type="button" onClick={() => setFitToScreen(value => !value)} aria-pressed={fitToScreen}><Scan size={13}/>{fitToScreen ? 'Full dashboard' : 'Fit screen'}</button></div></div>
        {error && <p className="sim-error" role="alert">{error}</p>}
        <div className="sim-view-grid"><RealTrack run={run} time={time} setTime={setTime} playing={playing} setPlaying={setPlaying}/><div>
          <div className="sim-chart-controls"><span>CHART WINDOW <b>{visibleChartRange[0].toFixed(3)}–{visibleChartRange[1].toFixed(3)} s</b></span><div><button aria-label="Zoom out on all charts" onClick={() => zoomCharts(1 / 2)} disabled={!chartRange}><ZoomOut size={14}/></button><button aria-label="Zoom in on all charts" onClick={() => zoomCharts(2)}><ZoomIn size={14}/></button><button aria-label="Fit full time range" onClick={resetChartZoom} disabled={!chartRange}><Scan size={14}/><span>Reset</span></button></div></div>
          <div className="sim-signal-grid">
          <MpcCostPanel points={series(run, 'mpcCost')} breakdown={series(run, 'mpcCostBreakdown')} time={time} range={visibleChartRange} onHover={setTime}/>
          <RealSignalChart title="Wheel speed" unit="m/s" points={speed} color="#60a5fa" time={time} range={visibleChartRange} onHover={setTime}/>
          <RealSignalChart title="Throttle command" unit="raw PWM" points={throttle} color="#f1b85b" time={time} range={visibleChartRange} onHover={setTime}/>
          <RealSignalChart title="Steering command" unit="raw PWM" points={steering} color="#a78bfa" time={time} range={visibleChartRange} onHover={setTime}/>
          <RealSignalChart title="IMU X acceleration" unit="m/s²" points={accel} color="#4adea5" time={time} range={visibleChartRange} onHover={setTime}/>
          <RealSignalChart title="Kart heading / GPS course" unit="deg" points={headingChart} color="#fb7185" time={time} range={visibleChartRange} onHover={setTime}/>
          <SelectedPointData run={run} time={time}/>
          </div></div></div>
      </section>
      <section className="sim-diagnostics" aria-label="Selected kart run diagnostics"><DiagnosticsPanel runId={runId} /></section>
      <footer className="sim-footer"><span>REAL KART TELEMETRY · AUTONOMOUSKART MCAP</span><span>{run ? `${speed.length.toLocaleString()} speed samples · ${valueText(run.duration)} s` : busy ? 'Loading selected bag…' : 'Select a real kart recording'} <CircleHelp size={12}/></span></footer>
    </main>
  </div>
}
