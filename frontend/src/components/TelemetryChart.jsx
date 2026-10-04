import { useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

function ChartTooltip({ active, payload, label, unit, xAxis }) {
  if (!active || !payload?.length) return null
  return <div className="chart-tooltip"><span>{xAxis === 'time' ? formatTime(label) : `${Number(label).toFixed(1)} m`}</span><strong>{payload[0].value}{unit}</strong></div>
}

export default function TelemetryChart({ title, subtitle, data, unit, domain, lines, zero = false, className = '', distance = 0, showAxisSelector = false }) {
  const [xAxis, setXAxis] = useState('time')
  const maxTime = data?.at(-1)?.time ?? 60
  const maxPosition = data?.reduce((max, point) => Math.max(max, Number(point.position ?? point.distance ?? 0)), 0) || distance || 0
  const plottedData = useMemo(() => (data ?? []).map((point) => ({
    ...point,
    position: Number(point.position ?? point.distance ?? (maxTime ? (point.time / maxTime) * (distance || maxPosition) : 0)),
  })), [data, distance, maxPosition, maxTime])
  const xMax = xAxis === 'time' ? maxTime : (maxPosition || distance)
  const ticks = Array.from({ length: 5 }, (_, i) => xMax * i / 4)
  const chartTitle = showAxisSelector ? `${title} vs. ${xAxis === 'time' ? 'time' : 'position'}` : title
  return <section className={`panel chart-panel ${className}`}>
    <div className="panel-title"><div><h3>{chartTitle}</h3><p>{subtitle}</p></div>{showAxisSelector && <label className="chart-axis-select"><span className="sr-only">Horizontal axis</span><select value={xAxis} onChange={(event) => setXAxis(event.target.value)} aria-label={`Horizontal axis for ${title}`}><option value="time">vs. time</option><option value="position">vs. position</option></select></label>}</div>
    <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={plottedData} margin={{ top: 12, right: 12, bottom: 0, left: -14 }}>
      <CartesianGrid vertical={false} stroke="#29332d" strokeDasharray="3 5" />
      <XAxis dataKey={xAxis} type="number" domain={[0, xMax || 'auto']} ticks={ticks} tickFormatter={xAxis === 'time' ? formatTime : (value) => `${Math.round(value)}`} tickLine={false} axisLine={false} tick={{ fill: '#849087', fontSize: 10, fontFamily: 'DM Mono' }} dy={8} />
      <YAxis domain={domain} tickLine={false} axisLine={false} tick={{ fill: '#849087', fontSize: 10, fontFamily: 'DM Mono' }} tickFormatter={(value) => `${value}`} width={38} />
      {zero && <ReferenceLine y={0} stroke="#47544a" />}
      <Tooltip content={<ChartTooltip unit={unit} xAxis={xAxis} />} cursor={{ stroke: '#59675c', strokeDasharray: '4 4' }} />
      {lines.map((line) => <Line key={line.key} type="monotone" dataKey={line.key} name={line.name} stroke={line.color} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#111712', strokeWidth: 2 }} isAnimationActive={false} />)}
      {lines.length > 1 && <Legend verticalAlign="top" align="right" height={22} iconType="circle" iconSize={6} wrapperStyle={{ color: '#9aa69d', fontSize: 10 }} />}
    </LineChart></ResponsiveContainer></div>
    <div className="axis-caption">{xAxis === 'time' ? 'TIME (MIN:SEC)' : 'POSITION (M)'}<span>{unit}</span></div>
  </section>
}
