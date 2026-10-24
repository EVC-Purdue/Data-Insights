import { useEffect, useRef, useState } from 'react'
import { analyzeRun, getDiagnostics } from '../api/api.js'

function Evidence({ items }) {
  return items.map(item => <details key={item.id}><summary>{item.id} · {item.signal || item.label || item.type} · {item.start ?? '?'}–{item.end ?? '?'} s · {item.unit || 'unit unavailable'}</summary>
    <pre>{JSON.stringify(item, null, 2)}</pre></details>)
}

export default function DiagnosticsPanel({ runId }) {
  const [data, setData] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const pending = useRef(null)
  const generation = useRef(0)
  useEffect(() => {
    generation.current += 1
    pending.current?.abort()
    setData(null); setAnalysis(null); setError(''); setBusy('')
    return () => pending.current?.abort()
  }, [runId])
  async function load(ai) {
    const current = generation.current
    const controller = new AbortController()
    pending.current = controller
    const timeout = setTimeout(() => controller.abort(), 65000)
    setBusy(ai ? 'Analyzing run…' : 'Calculating diagnostics…'); setError('')
    if (ai) setAnalysis(null)
    try {
      if (ai) {
        const result = await analyzeRun(runId, controller.signal)
        if (current === generation.current) setAnalysis(result)
      } else {
        const result = await getDiagnostics(runId, controller.signal)
        if (current === generation.current) setData(result)
      }
    } catch (e) {
      if (current === generation.current) setError(e.name === 'AbortError' ? 'Analysis request timed out or was cancelled.' : e.message)
    } finally {
      clearTimeout(timeout)
      if (current === generation.current) setBusy('')
    }
  }
  const report = analysis?.report
  return <section className="panel diagnostics-panel" aria-label="Run diagnostics">
    <h3>Run diagnostics</h3>
    <div className="diagnostic-controls">
      <button disabled={!runId || !!busy} onClick={() => load(false)}>Deterministic diagnostics</button>
      <button disabled={!runId || !!busy} onClick={() => load(true)}>Analyze Run</button>
    </div>
    <p>AI runs only when requested. It sends selected-run diagnostic data to OpenAI and provides advice only. Live analysis uses a snapshot.</p>
    {data?.aiConfigured === false && <p role="status">AI analysis not configured</p>}
    {busy && <p role="status">{busy}</p>}{error && <p role="alert">{error}</p>}
    {data && <details open><summary>Deterministic diagnostics · {data.events.length} reported events</summary>
      <p>Time basis: {data.metadata.time.basis}. {data.metadata.time.note}</p>
      {data.metadata.limitations.map((s, i) => <p key={i}>{s}</p>)}
      <div className="diagnostic-table"><table><thead><tr><th>Signal</th><th>Kind / unit</th><th>Samples / missing</th></tr></thead><tbody>
        {data.signals.map(s => <tr key={s.name}><td>{s.name}</td><td>{s.kind} / {s.unit || 'unknown'}</td><td>{s.samples} / {s.missing}</td></tr>)}
      </tbody></table></div>
      <p>{data.outcomeCheck.conclusion} Simulator label: {data.outcomeCheck.simulatorLabel || 'not supplied'}.</p>
      <Evidence items={data.events} />
      {data.truncated && <p>Showing the first 80 of {data.totalEvents} events.</p>}
      <details><summary>Numeric summaries and evidence</summary><Evidence items={data.summaries} /></details>
      <details><summary>Simulator-reported metrics and provenance</summary><p>{data.upstreamMetricProvenance}</p><pre>{JSON.stringify(data.upstreamMetrics, null, 2)}</pre></details>
    </details>}
    {report && <article>
      <h4>AI report · {report.status === 'insufficient_data' ? 'Insufficient data' : 'Analysis'}</h4>
      <p>{report.summary}</p><p>{analysis.provider} · {analysis.model} · {analysis.toolCalls} tool calls · {analysis.snapshot.start ?? '?'}–{analysis.snapshot.end ?? '?'} s ({analysis.snapshot.basis})</p>
      <h4>Observed issues</h4>{report.observed_issues.length === 0 && <p>No supported findings returned.</p>}
      {report.observed_issues.map((f, i) => <p key={i}><strong>{f.classification === 'simulator_label' ? 'Existing simulator label' : 'Observation'}:</strong> {f.finding} <small>Evidence: {f.evidence_ids.join(', ')}</small></p>)}
      <h4>Possible causes (hypotheses)</h4>{report.possible_causes.map((c, i) => <p key={i}>{c.hypothesis} — {c.uncertainty} <small>Evidence: {c.evidence_ids.join(', ')}</small></p>)}
      <h4>Uncertainty</h4><ul>{report.uncertainty.map((v, i) => <li key={i}>{v}</li>)}</ul>
      <h4>Recommended next checks</h4><ul>{report.recommended_next_checks.map((v, i) => <li key={i}>{v}</li>)}</ul>
      <h4>Supporting measurements / time windows</h4><Evidence items={report.evidence} />
    </article>}
  </section>
}
