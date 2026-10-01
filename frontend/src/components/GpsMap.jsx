import { Maximize2, MapPin } from 'lucide-react'

export default function GpsMap({ points }) {
  const path = points.map(({ x, y }, index) => `${index ? 'L' : 'M'}${x},${y}`).join(' ')
  return <section className="panel map-panel" id="trajectory"><div className="panel-title"><div><h3>GPS trajectory</h3><p>Representative mock path · one lap</p></div><button className="icon-button" aria-label="Map view"><Maximize2 size={15} /></button></div>
    <div className="map-viewport"><div className="map-lines" /><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Mock GPS path around a kart track"><path d={path} fill="none" stroke="#35513a" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /><path d={path} fill="none" stroke="#a5ed68" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /><circle cx={points[0].x} cy={points[0].y} r="2.1" fill="#a5ed68" vectorEffect="non-scaling-stroke" /><circle cx={points.at(-1).x} cy={points.at(-1).y} r="2.1" fill="#eff8eb" vectorEffect="non-scaling-stroke" /></svg><span className="map-tag map-start">START</span><span className="map-tag map-finish">FINISH</span><span className="map-place"><MapPin size={12} /> MOCK TRACK</span></div>
    <div className="map-legend"><span><i className="green-dot" />Start</span><span><i className="white-dot" />Finish</span><span className="map-caption">Track visualization uses mock GPS points</span></div>
  </section>
}
