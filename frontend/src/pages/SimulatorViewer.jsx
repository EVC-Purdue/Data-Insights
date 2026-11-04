import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, ChevronDown, CircleHelp, Gauge, MapPin, Play, Pause, Search, SlidersHorizontal } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getSimulatorJobs, getSimulatorEpisodes, getRunMeasurements, importSimulatorEpisode } from '../api/api.js'

const BASE_URL = 'https://evc.researchviewer.org'
const display = (value) => value == null ? '' : typeof value === 'object' ? value.ref || value.repo || value.name || JSON.stringify(value) : String(value)
const pretty = (value) => value == null ? '—' : typeof value === 'number' ? Number(value).toFixed(2) : display(value)
const labelOf = (item) => item?.label || item?.key?.slice(0, 10) || 'Episode'
const measure = (run, key) => run?.diagnostic?.measurements?.[key]?.samples || []
const displaySamples = (samples, limit = 2400) => {
  if (samples.length <= limit) return samples
  const stride = Math.ceil(samples.length / limit)
  const reduced = samples.filter((_, index) => index % stride === 0)
  if (reduced.at(-1) !== samples.at(-1)) reduced.push(samples.at(-1))
  return reduced
}

function Metric({ name, value, unit, help }) {
  return <div className="sim-metric" title={help}><span>{name}<i aria-hidden="true">i</i></span><strong>{pretty(value)}<small>{unit}</small></strong></div>
}

function SignalChart({ title, unit, data, color, second, secondName, onHover }) {
  const plotted = displaySamples(data.map((point, index) => ({ point, index })))
  const plot = plotted.map(({ point, index }) => ({ time: point.time, value: point.value, second: second?.[index]?.value }))
  return <section className="sim-chart">
    <header><strong>{title}</strong><span>{unit}</span></header>
    {plot.length ? <div className="sim-chart-plot"><ResponsiveContainer width="100%" height="100%"><LineChart data={plot} syncId="episode-time" syncMethod="value" onMouseMove={state => { if (state?.activeLabel != null) onHover(Number(state.activeLabel)) }} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
      <CartesianGrid stroke="#364252" vertical={false} strokeDasharray="3 5" />
      <XAxis dataKey="time" type="number" domain={['dataMin', 'dataMax']} tickLine={false} axisLine={false} tick={{ fill: '#aeb8c5', fontSize: 9 }} tickFormatter={v => `${Number(v).toFixed(0)}s`} />
      <YAxis width={36} tickLine={false} axisLine={false} tick={{ fill: '#aeb8c5', fontSize: 9 }} />
      <Tooltip contentStyle={{ background: '#192332', border: '1px solid #53647a', borderRadius: 5, fontSize: 11 }} labelFormatter={v => `${Number(v).toFixed(2)} s`} />
      <Line dataKey="value" name={title} stroke={color} dot={false} strokeWidth={1.8} isAnimationActive={false} connectNulls={false} />
      {second && <Line dataKey="second" name={secondName} stroke="#e8c66b" dot={false} strokeWidth={1.4} isAnimationActive={false} connectNulls={false} />}
    </LineChart></ResponsiveContainer></div> : <div className="sim-chart-empty">No signal recorded</div>}
  </section>
}

function Track({ run, time, playing, onTime, onToggle }) {
  const xSamples = measure(run, 'x'), ySamples = measure(run, 'y')
  const samples = displaySamples(xSamples.map((point, index) => ({ point, index }))).map(({ point, index }) => ({ x: point.value, y: ySamples[index]?.value, time: point.time })).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y))
  const bounds = samples.reduce((b, p) => ({ minX: Math.min(b.minX, p.x), maxX: Math.max(b.maxX, p.x), minY: Math.min(b.minY, p.y), maxY: Math.max(b.maxY, p.y) }), { minX: 0, maxX: 1, minY: 0, maxY: 1 })
  const { minX, maxX, minY, maxY } = bounds
  const span = Math.max(maxX - minX, maxY - minY, 1)
  const xy = p => [8 + (p.x - minX) / span * 84, 92 - (p.y - minY) / span * 84]
  const path = samples.map((p, i) => `${i ? 'L' : 'M'}${xy(p).join(',')}`).join(' ')
  const current = samples.reduce((best, p) => Math.abs(p.time - time) < Math.abs(best.time - time) ? p : best, samples[0])
  const yawSamples = measure(run, 'yaw')
  const heading = yawSamples.reduce((best, p) => Math.abs(p.time - time) < Math.abs(best.time - time) ? p : best, yawSamples[0])
  const headingDeg = heading && Number.isFinite(heading.value) ? ((heading.value * 180 / Math.PI + 360) % 360) : null
  if (!samples.length) return <section className="sim-track"><div className="sim-empty"><MapPin size={20} />Trajectory unavailable for this episode</div></section>
  return <section className="sim-track">
    <div className="sim-track-toolbar"><div className="sim-control-group"><button aria-label={playing ? 'Pause playback' : 'Play playback'} onClick={onToggle}>{playing ? <Pause size={14} /> : <Play size={14} />}</button><span>{playing ? 'Playing' : 'Paused'}</span></div><span>SIMULATION TRAJECTORY</span><span className="sim-heading-readout">HEADING <b>{headingDeg == null ? '—' : `${headingDeg.toFixed(0)}°`}</b></span></div>
    <svg viewBox="0 0 100 100" className="sim-track-svg" role="img" aria-label={`Episode trajectory; kart heading ${headingDeg == null ? 'unavailable' : `${headingDeg.toFixed(0)} degrees`}`}><path d={path} fill="none" stroke="#41536a" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/><path d={path} fill="none" stroke="#59b7d8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"/>{current && <g transform={`translate(${xy(current)[0]} ${xy(current)[1]})`}><circle r="4.5" fill="#192332" stroke="#f1b85b" strokeWidth="1.4" vectorEffect="non-scaling-stroke"/><path d="M0 -7 L3.5 2.5 L0 1 L-3.5 2.5 Z" fill="#f1b85b" transform={`rotate(${-(headingDeg ?? 0)})`} vectorEffect="non-scaling-stroke"/></g>}</svg>
    <div className="sim-track-caption"><span><i className="sim-dot start"/>START</span><span><i className="sim-dot current"/>KART POSITION + HEADING</span><span>{time.toFixed(1)} s</span></div>
    <input aria-label="Playback time" className="sim-timeline" type="range" min={samples[0].time} max={samples.at(-1).time} step="0.05" value={time} onChange={e => onTime(Number(e.target.value))}/>
  </section>
}

export default function SimulatorViewer() {
  const [jobs, setJobs] = useState([]), [jobId, setJobId] = useState(new URLSearchParams(location.search).get('job') || '')
  const [detail, setDetail] = useState(null), [run, setRun] = useState(null), [episodeId, setEpisodeId] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [query, setQuery] = useState('')
  const [kart, setKart] = useState('all'), [line, setLine] = useState('all'), [condition, setCondition] = useState('all'), [speed, setSpeed] = useState('all')
  const [episodeClass, setEpisodeClass] = useState('all')
  const [time, setTime] = useState(0), [playing, setPlaying] = useState(false)
  const abort = useRef(null)

  useEffect(() => {
    let alive = true
    getSimulatorJobs().then(list => { if (!alive) return; setJobs(list); if (!jobId && list.length) setJobId(list.find(x => x.status === 'done')?.id || list[0].id) }).catch(e => { if (alive) setError(e.message) })
    return () => { alive = false; abort.current?.abort() }
  }, [])

  useEffect(() => {
    if (!jobId) return
    let alive = true
    abort.current?.abort(); abort.current = new AbortController()
    setBusy(true); setError(''); setDetail(null); setRun(null); setEpisodeId('')
    getSimulatorEpisodes(jobId, abort.current.signal).then(value => { if (alive) setDetail(value) }).catch(e => { if (alive && e.name !== 'AbortError') setError(e.message) }).finally(() => { if (alive) setBusy(false) })
    const url = new URL(location.href); url.searchParams.set('job', jobId); history.replaceState({}, '', url)
    return () => { alive = false }
  }, [jobId])

  const episodes = detail?.episodes || []
  const fields = useMemo(() => {
    const parts = episodes.map(e => e.label.split(' / '))
    return {
      karts: [...new Set(parts.map(p => p[1]).filter(Boolean))],
      conditions: [...new Set(parts.map(p => p[0]).filter(Boolean))],
      classes: [...new Set(episodes.map(e => e.class || e.class_name).filter(Boolean))],
      lines: [...new Set(parts.map(p => p[2]?.split('@')[0]).filter(Boolean))],
      speeds: [...new Set(parts.map(p => p[2]?.split('@')[1]).filter(Boolean))],
    }
  }, [episodes])
  const visibleEpisodes = episodes.filter(e => {
    const parts = e.label.split(' / ')
    return (kart === 'all' || parts[1]?.toLowerCase() === kart) && (line === 'all' || parts[2]?.split('@')[0] === line) &&
      (condition === 'all' || parts[0] === condition) && (speed === 'all' || parts[2]?.split('@')[1] === speed) &&
      (episodeClass === 'all' || (e.class || e.class_name) === episodeClass)
  })
  const selectedEpisode = episodes.find(e => e.key === episodeId) || visibleEpisodes[0]
  useEffect(() => { if (!episodeId && selectedEpisode && !busy) chooseEpisode(selectedEpisode) }, [episodeId, selectedEpisode?.key, busy])
  useEffect(() => {
    if (!playing || !run) return
    const timer = setInterval(() => setTime(t => { const end = run.duration || 0; if (t >= end) { setPlaying(false); return 0 } return t + 0.08 }), 40)
    return () => clearInterval(timer)
  }, [playing, run])
  useEffect(() => { if (run) setTime(0) }, [run?.id])

  async function chooseEpisode(item) {
    setEpisodeId(item.key); setBusy(true); setError(''); setRun(null)
    try {
      const loaded = await importSimulatorEpisode(jobId, item.key)
      const diagnostic = await getRunMeasurements(loaded.id)
      setRun({ ...loaded, diagnostic }); setEpisodeId(item.key); setTime(0)
    }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const metrics = detail?.job?.metrics || detail?.metrics || detail?.job?.summary || {}
  const summaryValue = key => {
    return metrics[key]?.value ?? metrics[key]
  }
  const speedSamples = measure(run, 'speed'), cteSamples = measure(run, 'cte'), locSamples = measure(run, 'loc_err')
  const lapPercent = summaryValue('lap_completion')
  const safety = summaryValue('safety')
  const osc = summaryValue('oscillation_rate')

  return <div className="sim-app">
    <aside className="sim-sidebar">
      <a className="sim-brand" href="/"><span className="sim-brand-mark"><Activity size={16}/></span><b>EVC <i>SIM</i></b></a>
      <nav><a className="active" href="#jobs">Jobs</a><a href="#leaderboard">Leaderboard</a></nav>
      <div className="sim-side-section"><span>JOBS</span><label className="sim-search"><Search size={13}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter jobs"/></label>
        <div className="sim-job-list">{jobs.filter(j => `${j.name || j.tag || j.label || ''} ${j.id}`.toLowerCase().includes(query.toLowerCase())).map(j => <button key={j.id} className={jobId === j.id ? 'selected' : ''} onClick={() => setJobId(j.id)}><strong>{display(j.name || j.tag || j.label || j.id)}</strong><small>{display(j.tier || j.recipe?.tier)} · {display(j.status)}</small></button>)}</div>
      </div>
      <div className="sim-sidebar-foot"><i/>SIMULATOR DATA SOURCE<small><a href={BASE_URL} target="_blank" rel="noreferrer">evc.researchviewer.org</a></small></div>
    </aside>
    <main className="sim-main">
      <header className="sim-job-head"><div><div className="sim-breadcrumb">JOBS <span>/</span> {display(detail?.job?.tier) || 'SIMULATOR'}</div><h1>{display(detail?.job?.name || detail?.job?.tag || detail?.job?.label || jobId || 'Simulator runs')}</h1><p>{display(detail?.job?.recipe?.controller || detail?.job?.recipe?.source) || 'Autonomous vehicle evaluation'} <span>·</span> {display(detail?.job?.status) || 'Loading job'}</p></div><div className="sim-head-actions"><a className="sim-recordings-link" href="?source=recordings">Kart recordings</a><a className="sim-open-source" href={`${BASE_URL}/?job=${encodeURIComponent(jobId)}`} target="_blank" rel="noreferrer">Open in EVC viewer ↗</a></div></header>
      <section className="sim-filterbar"><label>🏎 <select value={kart} onChange={e => setKart(e.target.value)}><option value="all">All karts</option>{fields.karts.map(x => <option key={x} value={x.toLowerCase()}>{x}</option>)}</select><ChevronDown size={12}/></label><label><select value={line} onChange={e => setLine(e.target.value)}><option value="all">All lines</option>{fields.lines.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={12}/></label><label><select value={condition} onChange={e => setCondition(e.target.value)}><option value="all">All conditions</option>{fields.conditions.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={12}/></label><label><select value={episodeClass} onChange={e => setEpisodeClass(e.target.value)}><option value="all">All classes</option>{fields.classes.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={12}/></label><label><select value={speed} onChange={e => setSpeed(e.target.value)}><option value="all">All speeds</option>{fields.speeds.map(x => <option key={x}>{x}</option>)}</select><ChevronDown size={12}/></label><span className="sim-filter-count">{visibleEpisodes.length} episodes</span></section>
      <section className="sim-metrics">
        <Metric name="CTE P50" value={summaryValue('cte_p50')} unit="m" help="Median cross-track error: the distance between the kart and the target path."/><Metric name="CTE P90" value={summaryValue('cte_p90')} unit="m" help="90th-percentile cross-track error. P90 means 90% of measured errors were at or below this distance."/><Metric name="CTE P99" value={summaryValue('cte_p99')} unit="m" help="99th-percentile cross-track error; highlights the largest tracking deviations."/><Metric name="Safety" value={safety} unit="%" help="Simulator-reported safety score for this job."/><Metric name="Osc > 10 / 20 / 30" value={osc} unit="/s" help="Simulator oscillation metric at its 10, 20, and 30 thresholds; exact definition is reported by the simulator."/><Metric name="Laps" value={lapPercent} unit="%" help="Simulator-reported lap completion."/><Metric name="Loc RMS" value={summaryValue('loc_rms') ?? run?.diagnostic?.localizationMetrics?.rms} unit="m" help="Root-mean-square localization error, in meters."/>
      </section>
      <section className="sim-breakdown"><div className="sim-section-heading"><div><h2>Episode breakdown</h2><p>Choose a completed episode to inspect its trajectory and telemetry.</p></div><span>{busy ? 'LOADING…' : `${visibleEpisodes.length} SHOWN`}</span></div>
        <div className="sim-table-wrap"><table><thead><tr><th>Condition</th><th>Kart</th><th>Line</th><th>Class</th><th>Speed</th><th>Status</th><th>CTE P90</th><th>Outcome</th></tr></thead><tbody>{visibleEpisodes.slice(0, 120).map(item => { const p = item.label.split(' / '), lineSpeed = p[2]?.split('@') || []; return <tr key={item.key} className={selectedEpisode?.key === item.key ? 'chosen' : ''} onClick={() => chooseEpisode(item)}><td><button>{p[0] || '—'}</button></td><td>{p[1] || '—'}</td><td>{lineSpeed[0] || '—'}</td><td>{item.class || item.class_name || '—'}</td><td>{lineSpeed[1] || '—'}</td><td><span className="sim-status">{item.status || 'done'}</span></td><td>{pretty(item.metrics?.cte_p90)}</td><td>{item.outcome?.status || item.result || '—'}</td></tr> })}{!visibleEpisodes.length && <tr><td colSpan="8" className="sim-table-empty">{busy ? 'Loading simulator job…' : 'No episodes match these filters.'}</td></tr>}</tbody></table></div>
      </section>
      <section className="sim-viewer"><div className="sim-section-heading"><div><h2>Episode viewer</h2><p>{selectedEpisode ? `${labelOf(selectedEpisode)} · ${selectedEpisode.key.slice(0, 12)}` : 'Select an episode above'}</p></div><label className="sim-view-select">{selectedEpisode ? labelOf(selectedEpisode) : 'Select episode'}<select aria-label="Select episode" value={episodeId} onChange={e => { const item = episodes.find(ep => ep.key === e.target.value); if (item) chooseEpisode(item) }}><option value="">Select episode</option>{episodes.map(ep => <option value={ep.key} key={ep.key}>{labelOf(ep)} · {ep.key.slice(0, 8)}</option>)}</select><ChevronDown size={13}/></label></div>
        {error && <p className="sim-error" role="alert">{error}</p>}
        <div className="sim-view-grid"><Track run={run} time={time} playing={playing} onTime={setTime} onToggle={() => setPlaying(x => !x)}/><div className="sim-signal-grid">
          <SignalChart title="CTE" unit="m" data={cteSamples} color="#59c3d8" onHover={setTime}/>
          <SignalChart title="Steering" unit="deg" data={measure(run, 'wheel')} color="#a78bfa" second={measure(run, 'column')} secondName="Column" onHover={setTime}/>
          <SignalChart title="Speed" unit="m/s" data={speedSamples} color="#60a5fa" second={measure(run, 'cmd_speed')} secondName="Command" onHover={setTime}/>
          <SignalChart title="Lateral" unit="m/s²" data={measure(run, 'ay_mps2')} color="#f1b85b" onHover={setTime}/>
          <SignalChart title="Slide" unit="%" data={measure(run, 'slide_pct')} color="#fb7185" second={measure(run, 'lat_rear_pct')} secondName="Rear" onHover={setTime}/>
          <SignalChart title="Loc error" unit="m" data={locSamples} color="#4adea5" onHover={setTime}/>
        </div></div>
      </section>
      <footer className="sim-footer"><span>DATA FROM AUTONOMOUS SIMULATOR</span><span>{run ? `${speedSamples.length} speed samples · ${pretty(run.duration)} s` : busy ? 'Loading selected episode…' : 'Select an episode to load full telemetry'} <CircleHelp size={12}/></span></footer>
    </main>
  </div>
}
