import { Activity, Map, Radio } from 'lucide-react'

const links = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'signals', label: 'Telemetry signals', icon: Activity },
  { id: 'trajectory', label: 'GPS trajectory', icon: Map },
  { id: 'controller', label: 'MPC controller', icon: Radio },
]

export default function Sidebar({ usesMockData }) {
  return <aside className="sidebar">
    <a className="brand" href="#overview"><span className="brand-mark"><Activity size={18} /></span><span>KART<span className="brand-soft"> / INSIGHTS</span></span></a>
    <div className="side-caption">TELEMETRY</div>
    <nav aria-label="Dashboard sections">{links.map(({ id, label, icon: Icon }, index) => <a className={`side-link ${index === 0 ? 'selected' : ''}`} href={`#${id}`} key={id}><Icon size={16} /><span>{label}</span></a>)}</nav>
    <div className="sidebar-bottom"><span className="online-dot" />{usesMockData ? 'Mock data mode' : 'API mode'}<span className="sidebar-small">{usesMockData ? 'Configure VITE_API_URL to connect' : 'REST API configured'}</span></div>
  </aside>
}
