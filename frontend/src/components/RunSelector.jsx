import { ChevronDown, Route } from 'lucide-react'

export default function RunSelector({ runs, selectedId, onChange }) {
  const selected = runs.find((run) => run.id === selectedId) ?? runs[0]
  return <label className="run-selector"><span className="run-icon"><Route size={16} /></span><span className="run-selector-text"><small>SELECTED RUN</small><strong>{selected.name}</strong><em>{selected.date}</em></span><select value={selected.id} onChange={(event) => onChange(event.target.value)} aria-label="Select telemetry run">{runs.map((run) => <option value={run.id} key={run.id}>{run.name} — {run.date}</option>)}</select><ChevronDown className="select-chevron" size={15} /></label>
}
