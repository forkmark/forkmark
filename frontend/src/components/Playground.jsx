import { useState } from 'react'
import { api, dispatchApiError } from '../api.js'
import { PageHeader, pageStyle, formStyles as F, MODELS, divColor } from './ui'

const S = {
  form:     { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 },
  formFull: { gridColumn: '1 / -1' },
  textarea: { width: '100%', background: 'var(--surface2)', border: '1px solid var(--border)',
              borderRadius: 6, color: 'var(--text)', padding: '10px 12px', fontSize: 13,
              resize: 'vertical', boxSizing: 'border-box', minHeight: 120, fontFamily: 'var(--font)',
              lineHeight: 1.5 },
  sysArea:  { width: '100%', background: 'var(--surface2)', border: '1px solid var(--border)',
              borderRadius: 6, color: 'var(--text)', padding: '8px 10px', fontSize: 12,
              resize: 'vertical', boxSizing: 'border-box', minHeight: 60, fontFamily: 'var(--font)' },
  rangeRow: { display: 'flex', alignItems: 'center', gap: 8 },
  rangeVal: { fontSize: 12, color: 'var(--text)', fontWeight: 600, minWidth: 32 },
  numInput: { background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 5,
              color: 'var(--text)', padding: '7px 10px', fontSize: 12, width: 100, boxSizing: 'border-box' },
  runRow:   { display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 },
  runBtn:   (disabled) => ({
    background: disabled ? 'var(--border)' : 'var(--accent)', color: disabled ? 'var(--muted)' : 'var(--bg)',
    border: 'none', borderRadius: 6, padding: '10px 28px', fontSize: 14, fontWeight: 700,
    cursor: disabled ? 'not-allowed' : 'pointer',
  }),
  viewBtn:  { background: 'transparent', border: '1px solid var(--accent)', color: 'var(--accent)',
              borderRadius: 6, padding: '10px 20px', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  results:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  resCard:  (side) => ({
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderLeft: `3px solid ${side === 'A' ? 'var(--accent)' : 'var(--purple)'}`,
    borderRadius: '2px 8px 8px 2px', overflow: 'hidden',
  }),
  resHead:  () => ({
    padding: '10px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    borderBottom: '1px solid var(--border)', background: 'var(--surface2)',
  }),
  resSide:  (side) => ({ fontSize: 12, fontWeight: 700, color: side === 'A' ? 'var(--accent)' : 'var(--purple)' }),
  resMeta:  { fontSize: 10, color: 'var(--muted)', display: 'flex', gap: 10 },
  resBody:  { padding: '14px', fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap', color: 'var(--text)', maxHeight: 500, overflow: 'auto' },
  divBar:   { gridColumn: '1 / -1', textAlign: 'center', padding: 12, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 },
}

export default function Playground({ nav }) {
  const [prompt, setPrompt]       = useState('')
  const [systemPrompt, setSys]    = useState('')
  const [modelA, setModelA]       = useState('gpt-4o-mini')
  const [modelB, setModelB]       = useState('gpt-4o')
  const [customA, setCustomA]     = useState('')
  const [customB, setCustomB]     = useState('')
  const [tempA, setTempA]         = useState(0.7)
  const [tempB, setTempB]         = useState(0.7)
  const [maxA, setMaxA]           = useState(1024)
  const [maxB, setMaxB]           = useState(1024)
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [providers, setProviders] = useState([])
  const [provA, setProvA]         = useState('')
  const [provB, setProvB]         = useState('')

  // Load providers on mount
  useState(() => {
    api.listProviders().then(ps => setProviders(ps || [])).catch(() => {})
  })

  const showProviders = providers.length > 1
  const effModelA = modelA === '__custom__' ? customA.trim() : modelA
  const effModelB = modelB === '__custom__' ? customB.trim() : modelB
  const customMissing = (modelA === '__custom__' && !customA.trim()) ||
                        (modelB === '__custom__' && !customB.trim())

  async function run() {
    if (!prompt.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const data = await api.playgroundRun({
        prompt: prompt.trim(),
        model_a: effModelA,
        model_b: effModelB,
        system_prompt: systemPrompt.trim() || null,
        temperature_a: tempA,
        temperature_b: tempB,
        max_tokens_a: maxA,
        max_tokens_b: maxB,
        ...(provA ? { provider_id_a: provA } : {}),
        ...(provB ? { provider_id_b: provB } : {}),
      })
      setResult(data)
      window.dispatchEvent(new CustomEvent('fp:apisuccess', { detail: { message: 'Playground run complete' } }))
    } catch (err) {
      dispatchApiError(err.message || 'Playground run failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={pageStyle(1200)}>
      <PageHeader title="Prompt Playground" subtitle="Compare two models side-by-side on the same prompt" />

      <div style={S.form} data-layout="playground">
        <div style={S.formFull}>
          <label htmlFor="pg-prompt" style={F.label}>Prompt</label>
          <textarea id="pg-prompt" style={S.textarea} value={prompt} onChange={e => setPrompt(e.target.value)}
                    placeholder="Enter your prompt here..." />
        </div>
        <div style={S.formFull}>
          <label htmlFor="pg-system" style={F.label}>System Prompt (optional)</label>
          <textarea id="pg-system" style={S.sysArea} value={systemPrompt} onChange={e => setSys(e.target.value)}
                    placeholder="You are a helpful assistant..." />
        </div>
        {[
          { side: 'A', model: modelA, setModel: setModelA, custom: customA, setCustom: setCustomA,
            prov: provA, setProv: setProvA, temp: tempA, setTemp: setTempA, max: maxA, setMax: setMaxA },
          { side: 'B', model: modelB, setModel: setModelB, custom: customB, setCustom: setCustomB,
            prov: provB, setProv: setProvB, temp: tempB, setTemp: setTempB, max: maxB, setMax: setMaxB },
        ].map(col => (
          <div key={col.side}>
            <label htmlFor={`pg-model-${col.side}`} style={F.label}>Model {col.side}</label>
            <select id={`pg-model-${col.side}`} style={F.select} value={col.model}
                    onChange={e => col.setModel(e.target.value)}>
              {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              <option value="__custom__">Custom model ID…</option>
            </select>
            {col.model === '__custom__' && (
              <input style={{ ...F.select, marginTop: 6 }}
                     placeholder="e.g. openai/gpt-4o, llama3, claude-3-5-sonnet"
                     value={col.custom} onChange={e => col.setCustom(e.target.value)} />
            )}
            {showProviders && (
              <div style={{ marginTop: 6 }}>
                <label style={{ fontSize: 10, color: 'var(--muted)', display: 'block', marginBottom: 3 }}>Provider</label>
                <select style={F.select} value={col.prov} onChange={e => col.setProv(e.target.value)}>
                  <option value="">Default{providers.find(p => p.is_default) ? ` (${providers.find(p => p.is_default).name})` : ''}</option>
                  {providers.filter(p => !p.is_default).map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}
            <div style={{ marginTop: 10 }}>
              <label style={F.label}>Temperature: {col.temp.toFixed(1)}</label>
              <div style={S.rangeRow}>
                <input style={{ flex:1 }} type="range" min="0" max="2" step="0.1"
                       value={col.temp} onChange={e => col.setTemp(parseFloat(e.target.value))} />
                <span style={S.rangeVal}>{col.temp.toFixed(1)}</span>
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              <label style={F.label}>Max Tokens</label>
              <input style={S.numInput} type="number" value={col.max} min={1} max={16384}
                     onChange={e => col.setMax(parseInt(e.target.value) || 1024)} />
            </div>
          </div>
        ))}
      </div>

      <div style={S.runRow}>
        <button style={S.runBtn(!prompt.trim() || loading || customMissing)}
                disabled={!prompt.trim() || loading || customMissing} onClick={run}>
          {loading ? 'Running...' : 'Run Comparison'}
        </button>
        {result?.comparison_id && (
          <button style={S.viewBtn} onClick={() => nav('compare', { compId: result.comparison_id })}>
            View Full Comparison
          </button>
        )}
      </div>

      {result && (
        <div style={S.results} data-layout="playground">
          {['A', 'B'].map(side => {
            const r = side === 'A' ? result.model_a : result.model_b
            return (
              <div key={side} style={S.resCard(side)}>
                <div style={S.resHead()}>
                  <span style={S.resSide(side)}>{side} — {r?.model_id}</span>
                  <div style={S.resMeta}>
                    <span>{r?.latency_ms}ms</span>
                    <span>{r?.tokens_input}↑ {r?.tokens_output}↓</span>
                  </div>
                </div>
                <div style={S.resBody}>{r?.output_text || '(no output)'}</div>
              </div>
            )
          })}
          <div style={S.divBar}>
            Divergence:{' '}
            <span style={{ fontWeight:700, fontSize:13, color: divColor(result.divergence_score) }}>
              {(result.divergence_score * 100).toFixed(0)}%
            </span>
            {result.divergence_summary && (
              <span style={{ marginLeft:10, color:'var(--muted)', fontSize:12 }}>{result.divergence_summary}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
