import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null
  return <div className="chart-tooltip"><span>{formatTime(label)}</span><strong>{payload[0].value}{unit}</strong></div>
}

export default function TelemetryChart({ title, subtitle, data, unit, domain, lines, zero = false, className = '' }) {
  const maxTime = data?.at(-1)?.time ?? 60
  const interval = Math.max(1, Math.ceil(maxTime / 4 / 5) * 5)
  const ticks = Array.from({ length: 5 }, (_, i) => Math.min(maxTime, i * interval))
  return <section className={`panel chart-panel ${className}`}>
    <div className="panel-title"><div><h3>{title}</h3><p>{subtitle}</p></div></div>
    <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -14 }}>
      <CartesianGrid vertical={false} stroke="#29332d" strokeDasharray="3 5" />
      <XAxis dataKey="time" ticks={ticks} tickFormatter={formatTime} tickLine={false} axisLine={false} tick={{ fill: '#849087', fontSize: 10, fontFamily: 'DM Mono' }} dy={8} />
      <YAxis domain={domain} tickLine={false} axisLine={false} tick={{ fill: '#849087', fontSize: 10, fontFamily: 'DM Mono' }} tickFormatter={(value) => `${value}`} width={38} />
      {zero && <ReferenceLine y={0} stroke="#47544a" />}
      <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: '#59675c', strokeDasharray: '4 4' }} />
      {lines.map((line) => <Line key={line.key} type="monotone" dataKey={line.key} name={line.name} stroke={line.color} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#111712', strokeWidth: 2 }} isAnimationActive={false} />)}
      {lines.length > 1 && <Legend verticalAlign="top" align="right" height={22} iconType="circle" iconSize={6} wrapperStyle={{ color: '#9aa69d', fontSize: 10 }} />}
    </LineChart></ResponsiveContainer></div>
    <div className="axis-caption">TIME (MIN:SEC)<span>{unit}</span></div>
  </section>
}
