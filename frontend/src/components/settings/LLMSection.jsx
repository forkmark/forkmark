import { useState } from 'react'
import { S, DEFAULT_MODELS, SCORER_OPTIONS } from './shared.jsx'
import { InfoTip } from '../ui'

const advToggle = {
  fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none',
  cursor: 'pointer', padding: '4px 0', marginTop: 8, fontWeight: 500,
}

export default function LLMSection({
  apiKey, setApiKey, keySet, keyMask,
  baseUrl, setBaseUrl,
  judgeModel, setJudgeModel, customModel, setCustomModel,
  scorer, setScorer, stModel, setStModel, embedModel, setEmbedModel,
}) {
  const [focused, setFocused] = useState(null)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const isOpenRouter = baseUrl.includes('openrouter')
  const scorerInfo = SCORER_OPTIONS.find(o => o.value === scorer)

  return (
    <>
      <div style={S.section}>LLM Configuration</div>

      {/* Provider Card */}
      <div style={S.card}>
        <h2 style={S.cardH}>LLM Provider</h2>
        <p style={S.cardSub}>
          Used for the No-code Workflow Runner and automatic divergence scoring.
          Compatible with OpenAI and any OpenAI-compatible provider (OpenRouter, Groq, Together, Ollama, etc.).
        </p>

        <div style={S.row}>
          <label htmlFor="settings-api-key" style={S.label}>API Key</label>
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <div style={{ flex:1, position:'relative' }}>
              <input
                id="settings-api-key"
                type="password"
                style={{ ...S.input, borderColor: focused === 'key' ? 'var(--accent)' : 'var(--border)' }}
                placeholder={keySet ? `Current key: ${keyMask} — paste new key to replace` : 'sk-...  or  sk-or-v1-...'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                onFocus={() => setFocused('key')}
                onBlur={() => setFocused(null)}
                autoComplete="off"
              />
            </div>
            <span style={S.badge(keySet)}>
              <span style={S.dot(keySet)} />
              {keySet ? 'Set' : 'Not set'}
            </span>
          </div>
          <p style={S.hint}>
            Key is stored in the platform database (not sent to the browser after saving).
            For OpenRouter, use your <code>sk-or-v1-…</code> key and set the Base URL below.
          </p>
        </div>

        <div style={S.row}>
          <label htmlFor="settings-base-url" style={S.label}>Base URL <span style={{ fontWeight:400, textTransform:'none', letterSpacing:0 }}>(optional — leave blank for OpenAI)</span></label>
          <input
            id="settings-base-url"
            style={{ ...S.input, borderColor: focused === 'url' ? 'var(--accent)' : 'var(--border)' }}
            placeholder="https://openrouter.ai/api/v1"
            value={baseUrl}
            onChange={e => setBaseUrl(e.target.value)}
            onFocus={() => setFocused('url')}
            onBlur={() => setFocused(null)}
          />
          {isOpenRouter && (
            <p style={{ ...S.hint, color:'var(--accent)' }}>
              OpenRouter detected — use <code>openai/gpt-4o</code> or <code>anthropic/claude-3-5-sonnet</code> style model IDs below.
            </p>
          )}
        </div>
      </div>

      {/* Judge Model Card */}
      <div style={S.card}>
        <h2 style={S.cardH}>LLM-as-Judge Model<InfoTip text="This model automatically scores how different the two branch outputs are. A fast, cheap model like gpt-4o-mini works well for most use cases. You only pay for it when running comparisons." /></h2>
        <p style={S.cardSub}>
          Model used to auto-score divergence between Branch A and Branch B outputs.
          A faster, cheaper model (gpt-4o-mini) works well for most use cases.
        </p>

        <div style={S.row}>
          <label htmlFor="settings-judge-model" style={S.label}>Model</label>
          <div style={{ display:'flex', gap:8 }}>
            <select
              id="settings-judge-model"
              style={{ ...S.input, flex:1 }}
              value={customModel ? '__custom__' : (judgeModel || 'gpt-4o-mini')}
              onChange={e => {
                if (e.target.value === '__custom__') {
                  setCustomModel(judgeModel || '')
                  setJudgeModel('')
                } else {
                  setJudgeModel(e.target.value)
                  setCustomModel('')
                }
              }}
            >
              {DEFAULT_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              <option value="__custom__">Custom model ID…</option>
            </select>
          </div>
          {customModel !== '' && (
            <input
              style={{ ...S.input, marginTop:8, borderColor: focused === 'judge' ? 'var(--accent)' : 'var(--border)' }}
              placeholder="e.g. mistralai/mixtral-8x7b-instruct"
              value={customModel}
              onChange={e => setCustomModel(e.target.value)}
              onFocus={() => setFocused('judge')}
              onBlur={() => setFocused(null)}
            />
          )}
          <p style={S.hint}>Current judge model: <strong>{customModel || judgeModel || 'gpt-4o-mini'}</strong></p>
        </div>
      </div>

      {/* Divergence Scorer Card */}
      <div style={S.card}>
        <h2 style={S.cardH}>How to Measure Differences</h2>
        <p style={S.cardSub}>
          When two model outputs are compared, Forkmark scores how different they are.
          Pick a strategy based on your needs — Auto works well for most teams.
        </p>

        <div style={S.row}>
          <label htmlFor="settings-scorer" style={S.label}>Scoring Strategy</label>
          <select
            id="settings-scorer"
            style={{ ...S.input }}
            value={scorer}
            onChange={e => setScorer(e.target.value)}
          >
            {SCORER_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <p style={S.hint}>{scorerInfo?.desc}</p>
          {scorerInfo?.dep && (
            <p style={{ ...S.hint, color:'var(--orange)', marginTop:2 }}>
              Requires: {scorerInfo.dep}
            </p>
          )}
        </div>

        {/* Quick comparison table */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, margin:'12px 0' }}>
          {[
            { label:'Fast & Free', value:'auto', color:'var(--green)' },
            { label:'Better Accuracy', value:'semantic', color:'var(--accent)' },
            { label:'Most Accurate', value:'llm_judge', color:'var(--purple)' },
          ].map(t => (
            <button key={t.value} onClick={() => setScorer(t.value)} style={{
              padding:'10px 8px', borderRadius:6, fontSize:11, fontWeight:600, cursor:'pointer',
              background: scorer === t.value ? t.color + '18' : 'var(--bg)',
              border: `1px solid ${scorer === t.value ? t.color : 'var(--border)'}`,
              color: scorer === t.value ? t.color : 'var(--muted)',
              textAlign:'center', transition:'all 0.15s',
            }}>
              {t.label}
              {t.value === 'auto' && <div style={{ fontSize:9, marginTop:2, opacity:0.7 }}>Recommended</div>}
              {t.value === 'llm_judge' && <div style={{ fontSize:9, marginTop:2, opacity:0.7 }}>~$0.001/comparison</div>}
            </button>
          ))}
        </div>

        {/* Advanced section (collapsed by default) */}
        <button style={advToggle} onClick={() => setShowAdvanced(v => !v)}>
          {showAdvanced ? '▾ Hide' : '▸ Show'} advanced options
        </button>

        {showAdvanced && (
          <div style={{ marginTop:12, padding:'12px', background:'var(--bg)', borderRadius:6, border:'1px solid var(--border)' }}>
            {scorerInfo?.detail && (
              <p style={{ ...S.hint, marginBottom:8 }}>
                <strong>Technical detail:</strong> {scorerInfo.detail}
              </p>
            )}

            {scorer === 'semantic' && (
              <div style={S.row}>
                <label htmlFor="settings-st-model" style={S.label}>Sentence-Transformers Model</label>
                <input
                  id="settings-st-model"
                  style={{ ...S.input, borderColor: focused === 'st' ? 'var(--accent)' : 'var(--border)' }}
                  placeholder="all-MiniLM-L6-v2"
                  value={stModel}
                  onChange={e => setStModel(e.target.value)}
                  onFocus={() => setFocused('st')}
                  onBlur={() => setFocused(null)}
                />
                <p style={S.hint}>Model name from HuggingFace sentence-transformers. Default: all-MiniLM-L6-v2</p>
              </div>
            )}

            {scorer === 'openai' && (
              <div style={S.row}>
                <label htmlFor="settings-embed-model" style={S.label}>Embedding Model</label>
                <input
                  id="settings-embed-model"
                  style={{ ...S.input, borderColor: focused === 'embed' ? 'var(--accent)' : 'var(--border)' }}
                  placeholder="text-embedding-3-small"
                  value={embedModel}
                  onChange={e => setEmbedModel(e.target.value)}
                  onFocus={() => setFocused('embed')}
                  onBlur={() => setFocused(null)}
                />
                <p style={S.hint}>OpenAI embedding model ID. Default: text-embedding-3-small</p>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
