import { Activity, Check, Cpu, Gauge, Radio } from 'lucide-react'
import TelemetryChart from './TelemetryChart.jsx'

export default function ControllerPanel({ controller, data = [], measuredData = [] }) {
  const hasCommandedSpeed = data.some((point) => Number.isFinite(point.target))
  const hasMeasuredSeries = data.some((point) => Number.isFinite(point.actual))
  const chartData = hasMeasuredSeries ? data : measuredData.map(({ time, value, position }) => ({ time, position, actual: value }))
  const chartLines = hasCommandedSpeed
    ? [{ key: 'target', name: 'Target', color: '#72b9fa' }, { key: 'actual', name: 'Actual', color: '#a5ed68' }]
    : [{ key: 'actual', name: 'Measured', color: '#a5ed68' }]
  const chartTitle = hasCommandedSpeed ? 'Commanded vs. actual speed' : 'Measured speed'
  const chartSubtitle = hasCommandedSpeed
    ? 'Target speed compared with measured speed'
    : 'Target speed is unavailable for this data source'

  return <section className="panel controller-panel" id="controller"><div className="panel-title"><div><h3>MPC / controller</h3><p>{hasCommandedSpeed ? 'Commanded speed compared with measured speed' : 'Measured speed; target command is unavailable'}</p></div><span className="health-badge"><i />{controller?.health ?? 'Unavailable'}</span></div>
    <div className="controller-metrics"><div><span className="controller-metric-icon"><Cpu size={15} /></span><span><small>MODE</small><b>{controller?.mode ?? 'Unavailable'}</b></span></div><div><span className="controller-metric-icon"><Activity size={15} /></span><span><small>STATUS MESSAGE RATE</small><b>{controller?.frequency == null ? 'Unavailable' : `${controller.frequency.toFixed(1)} Hz`}</b></span></div><div><span className="controller-metric-icon"><Gauge size={15} /></span><span><small>MEAN TRACKING ERROR</small><b>{controller?.trackingError == null ? 'Unavailable' : `${controller.trackingError.toFixed(2)} m/s`}</b></span></div><div><span className="controller-metric-icon"><Radio size={15} /></span><span><small>STATUS MESSAGES</small><b>{controller?.messages?.toLocaleString() ?? 'Unavailable'}</b></span></div></div>
    <TelemetryChart title={chartTitle} subtitle={chartSubtitle} data={chartData} unit=" m/s" domain={[0, 'auto']} lines={chartLines} className="controller-chart" />
  </section>
}
