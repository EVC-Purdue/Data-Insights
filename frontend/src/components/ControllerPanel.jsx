import { Activity, Check, Cpu, Gauge, Radio } from 'lucide-react'
import TelemetryChart from './TelemetryChart.jsx'

export default function ControllerPanel({ controller, data }) {
  return <section className="panel controller-panel" id="controller"><div className="panel-title"><div><h3>MPC / controller</h3><p>Commanded speed compared with measured speed</p></div><span className="health-badge"><i />{controller.health}</span></div>
    <div className="controller-metrics"><div><span className="controller-metric-icon"><Cpu size={15} /></span><span><small>MODE</small><b>{controller.mode}</b></span></div><div><span className="controller-metric-icon"><Activity size={15} /></span><span><small>UPDATE RATE</small><b>{controller.frequency} Hz</b></span></div><div><span className="controller-metric-icon"><Gauge size={15} /></span><span><small>MEAN TRACKING ERROR</small><b>{controller.trackingError.toFixed(2)} m/s</b></span></div><div><span className="controller-metric-icon"><Radio size={15} /></span><span><small>STATUS MESSAGES</small><b>{controller.messages.toLocaleString()}</b></span></div></div>
    <TelemetryChart title="Commanded vs. actual speed" subtitle="Mock MPC target compared with kart speed" data={data} unit=" m/s" domain={[0, 'auto']} lines={[{ key: 'target', name: 'Target', color: '#72b9fa' }, { key: 'actual', name: 'Actual', color: '#a5ed68' }]} className="controller-chart" />
  </section>
}
