export default function StatCard({ label, value, unit, detail, icon: Icon, tone }) {
  return <article className="stat-card"><div className="stat-label">{label}<span className={`stat-icon ${tone}`}><Icon size={17} /></span></div><div className="stat-value">{value}<small>{unit}</small></div><div className="stat-detail">{detail}</div></article>
}
