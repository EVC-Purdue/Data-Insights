import { Maximize2, MapPin } from 'lucide-react'

export default function GpsMap({ points = [], usesMockData = false }) {
  if (!points.length) return <section className="panel map-panel"><h3>GPS trajectory</h3><p>Unavailable for this run.</p></section>
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const minX = Math.min(...xs), minY = Math.min(...ys)
  const extent = Math.max(Math.max(...xs) - minX, Math.max(...ys) - minY, 1)
  points = points.map(p => ({ x: 5 + (p.x - minX) / extent * 90, y: 95 - (p.y - minY) / extent * 90 }))
  const path = points.map(({ x, y }, index) => `${index ? 'L' : 'M'}${x},${y}`).join(' ')
  return <section className="panel map-panel" id="trajectory"><div className="panel-title"><div><h3>GPS trajectory</h3><p>{usesMockData ? 'Sample path' : 'Recorded local position /gps'}</p></div><button className="icon-button" aria-label="Map view"><Maximize2 size={15} /></button></div>
    <div className="map-viewport"><div className="map-lines" /><svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Run trajectory"><path d={path} fill="none" stroke="#35513a" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /><path d={path} fill="none" stroke="#a5ed68" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /><circle cx={points[0].x} cy={points[0].y} r="2.1" fill="#a5ed68" vectorEffect="non-scaling-stroke" /><circle cx={points.at(-1).x} cy={points.at(-1).y} r="2.1" fill="#eff8eb" vectorEffect="non-scaling-stroke" /></svg><span className="map-tag map-start">START</span><span className="map-tag map-finish">FINISH</span><span className="map-place"><MapPin size={12} /> {usesMockData ? 'MOCK TRACK' : 'RECORDED PATH'}</span></div>
    <div className="map-legend"><span><i className="green-dot" />Start</span><span><i className="white-dot" />Finish</span><span className="map-caption">{usesMockData ? 'Sample GPS points' : 'Local coordinates scaled to fit; not a geographic map'}</span></div>
  </section>
}
