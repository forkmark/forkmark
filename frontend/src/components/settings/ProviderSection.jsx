import { useState, useEffect, useCallback } from 'react'
import { api, dispatchApiError } from '../../api.js'
import { S } from './shared.jsx'
import { InfoTip } from '../ui'

const PROVIDER_TYPES = [
  { value: 'openai',     label: 'OpenAI',     hint: 'GPT-4o, GPT-4o-mini, o1, o3' },
  { value: 'anthropic',  label: 'Anthropic',   hint: 'Claude 3.5 Sonnet, Haiku, Opus' },
  { value: 'openrouter', label: 'OpenRouter',  hint: 'Unified access to 100+ models' },
  { value: 'ollama',     label: 'Ollama',      hint: 'Local models — Llama, Mistral' },
  { value: 'custom',     label: 'Custom',      hint: 'Any OpenAI-compatible API' },
]

const PS = {
  list: { display: 'flex', flexDirection: 'column', gap: 8 },
  item: (isDefault) => ({
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '12px 16px', borderRadius: '2px 8px 8px 2px',
    background: isDefault ? 'rgba(123,164,247,0.04)' : 'var(--surface)',
    border: '1px solid var(--border)',
    borderLeft: `3px solid ${isDefault ? 'var(--accent)' : 'var(--border)'}`,
    transition: 'all 0.15s',
  }),
  itemInfo: { flex: 1, minWidth: 0 },
  itemName: { fontSize: 13, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.01em' },
  itemMeta: { fontSize: 11, color: 'var(--muted)', marginTop: 2 },
  defaultBadge: {
    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    padding: '2px 6px', borderRadius: 4,
    background: 'rgba(123,164,247,0.15)', color: 'var(--accent)',
  },
  keyBadge: (set) => ({
    fontSize: 10, padding: '2px 6px', borderRadius: 4,
    background: set ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
    color: set ? 'var(--green)' : 'var(--red)',
  }),
  actionBtn: {
    background: 'none', border: 'none', color: 'var(--muted)',
    cursor: 'pointer', fontSize: 12, padding: '4px 8px', borderRadius: 4,
  },
  addBtn: {
    padding: '8px 16px', borderRadius: 6, fontSize: 12, fontWeight: 600,
    background: 'var(--accent)', color: 'var(--bg)', border: 'none',
    cursor: 'pointer',
  },
  empty: {
    padding: '24px', textAlign: 'center', fontSize: 13,
    color: 'var(--muted)', borderRadius: 8,
    background: 'var(--surface)', border: '1px dashed var(--border)',
  },
  formRow: { marginBottom: 12 },
  formGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 },
  testBtn: (testing) => ({
    padding: '6px 14px', borderRadius: 6, fontSize: 11, fontWeight: 600,
    background: testing ? 'var(--surface2)' : 'var(--surface)',
    border: '1px solid var(--border)', color: 'var(--text)',
    cursor: testing ? 'default' : 'pointer',
  }),
  testResult: (ok) => ({
    fontSize: 11, marginTop: 6, padding: '6px 10px', borderRadius: 4,
    background: ok ? 'rgba(74,222,128,0.08)' : 'rgba(248,113,113,0.08)',
    color: ok ? 'var(--green)' : 'var(--red)',
  }),
}

function ProviderForm({ provider, onSave, onCancel }) {
  const [name, setName] = useState(provider?.name || '')
  const [ptype, setPtype] = useState(provider?.provider_type || 'openai')
  const [baseUrl, setBaseUrl] = useState(provider?.base_url || '')
  const [apiKey, setApiKey] = useState('')
  const [isDefault, setIsDefault] = useState(provider?.is_default || false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [nameError, setNameError] = useState(false)

  const isEdit = !!provider

  async function handleSave() {
    if (!name.trim()) { setNameError(true); return }
    setSaving(true)
    try {
      if (isEdit) {
        const body = { name: name.trim(), provider_type: ptype, base_url: baseUrl.trim() }
        if (apiKey.trim()) body.api_key = apiKey.trim()
        if (isDefault) body.is_default = true
        await api.updateProvider(provider.id, body)
      } else {
        await api.createProvider({
          name: name.trim(), provider_type: ptype,
          base_url: baseUrl.trim(), api_key: apiKey.trim(),
          is_default: isDefault,
        })
      }
      window.dispatchEvent(new CustomEvent('fp:apisuccess', {
        detail: { message: `Provider ${isEdit ? 'updated' : 'added'}` }
      }))
      onSave()
    } catch (e) {
      dispatchApiError(e.message || 'Failed to save provider')
    } finally {
      setSaving(false)
    }
  }

  async function handleTest() {
    if (!isEdit) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testProvider(provider.id)
      setTestResult(result)
    } catch (e) {
      setTestResult({ ok: false, message: e.message || 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  const typeInfo = PROVIDER_TYPES.find(t => t.value === ptype)

  return (
    <div style={{ ...S.card, borderColor: 'var(--accent)', borderWidth: 1 }}>
      <h2 style={S.cardH}>{isEdit ? 'Edit Provider' : 'Add Provider'}</h2>

      <div style={PS.formGrid}>
        <div style={PS.formRow}>
          <label style={S.label}>Name <span style={{ color: 'var(--red)' }}>*</span></label>
          <input style={{ ...S.input, borderColor: nameError ? 'var(--red)' : undefined }}
            placeholder='e.g. "OpenAI Production"'
            value={name}
            onChange={e => { setName(e.target.value); if (nameError) setNameError(false) }}
            aria-invalid={nameError} autoFocus />
          {nameError && <p style={{ ...S.hint, color: 'var(--red)' }}>Name is required.</p>}
        </div>
        <div style={PS.formRow}>
          <label style={S.label}>Type</label>
          <select style={S.input} value={ptype} onChange={e => setPtype(e.target.value)}>
            {PROVIDER_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          {typeInfo && <p style={S.hint}>{typeInfo.hint}</p>}
        </div>
      </div>

      <div style={PS.formRow}>
        <label style={S.label}>
          Base URL <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span>
        </label>
        <input style={S.input}
          placeholder={ptype === 'ollama' ? 'http://localhost:11434/v1' :
                       ptype === 'openrouter' ? 'https://openrouter.ai/api/v1' :
                       ptype === 'anthropic' ? 'https://api.anthropic.com' :
                       'Leave blank for default'}
          value={baseUrl} onChange={e => setBaseUrl(e.target.value)} />
      </div>

      <div style={PS.formRow}>
        <label style={S.label}>API Key</label>
        <input type="password" style={S.input}
          placeholder={isEdit && provider.api_key_set
            ? `Current key: ${provider.api_key_masked} — paste new to replace`
            : 'sk-... or key-...'}
          value={apiKey} onChange={e => setApiKey(e.target.value)}
          autoComplete="off" />
        <p style={S.hint}>Encrypted at rest. Never displayed after saving.</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={isDefault}
            onChange={e => setIsDefault(e.target.checked)} />
          Set as default provider
        </label>
        <InfoTip text="The default provider is used when no specific provider is selected for a branch." />
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button style={S.btn(true, saving)} disabled={saving} onClick={handleSave}>
          {saving ? 'Saving…' : isEdit ? 'Update Provider' : 'Add Provider'}
        </button>
        {isEdit && (
          <button style={PS.testBtn(testing)} disabled={testing} onClick={handleTest}>
            {testing ? 'Testing…' : '⚡ Test Connection'}
          </button>
        )}
        <button style={{ ...PS.actionBtn, marginLeft: 'auto' }} onClick={onCancel}>
          Cancel
        </button>
      </div>

      {testResult && (
        <div style={PS.testResult(testResult.ok)}>
          {testResult.ok ? '✓ ' : '✕ '}{testResult.message}
          {testResult.latency_ms > 0 && ` (${testResult.latency_ms}ms)`}
        </div>
      )}
    </div>
  )
}

export default function ProviderSection() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editProvider, setEditProvider] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    api.listProviders()
      .then(ps => setProviders(ps || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDelete(id) {
    setDeleting(id)
    try {
      await api.deleteProvider(id)
      window.dispatchEvent(new CustomEvent('fp:apisuccess', {
        detail: { message: 'Provider deleted' }
      }))
      load()
    } catch (e) {
      dispatchApiError(e.message || 'Failed to delete provider')
    } finally {
      setDeleting(null)
    }
  }

  async function handleSetDefault(id) {
    try {
      await api.updateProvider(id, { is_default: true })
      window.dispatchEvent(new CustomEvent('fp:apisuccess', {
        detail: { message: 'Default provider updated' }
      }))
      load()
    } catch (e) {
      dispatchApiError(e.message || 'Failed to update default')
    }
  }

  function handleFormDone() {
    setShowForm(false)
    setEditProvider(null)
    load()
  }

  return (
    <>
      <div style={S.section}>
        LLM Providers
        <InfoTip text="Configure one or more LLM providers. Each comparison branch can use a different provider, enabling cross-provider A/B testing." />
      </div>

      <div style={S.card}>
        <h2 style={S.cardH}>Provider Registry</h2>
        <p style={S.cardSub}>
          <strong>Where your models run.</strong> Add a provider for each LLM endpoint (OpenAI, Anthropic,
          Ollama, …). Each comparison branch can use a different provider — handy for OpenAI vs. Anthropic or
          production vs. staging keys. The judge model and divergence-scoring settings live below in
          <em> LLM Configuration</em>.
        </p>

        {/* Provider list */}
        {loading ? (
          <div style={{ padding: 20, color: 'var(--muted)', fontSize: 12 }}>Loading providers…</div>
        ) : providers.length === 0 && !showForm ? (
          <div style={PS.empty}>
            <div style={{ fontSize: 24, marginBottom: 8, opacity: 0.4 }}>🔌</div>
            <div style={{ marginBottom: 4 }}>No providers configured yet</div>
            <div style={{ fontSize: 11, marginBottom: 12, maxWidth: 340, margin: '0 auto 12px' }}>
              Add an LLM provider to get started. You can also continue using the
              API key in the LLM Configuration section below — it will be auto-migrated.
            </div>
            <button style={PS.addBtn} onClick={() => setShowForm(true)}>
              + Add Provider
            </button>
          </div>
        ) : (
          <>
            <div style={PS.list}>
              {providers.map(p => (
                <div key={p.id} style={PS.item(p.is_default)}>
                  <div style={PS.itemInfo}>
                    <div style={PS.itemName}>
                      {p.name}
                      {p.is_default && (
                        <span style={{ ...PS.defaultBadge, marginLeft: 8 }}>Default</span>
                      )}
                    </div>
                    <div style={PS.itemMeta}>
                      {(PROVIDER_TYPES.find(t => t.value === p.provider_type) || {}).label || p.provider_type}
                      {p.base_url && <> · <code style={{ fontSize: 10 }}>{p.base_url}</code></>}
                    </div>
                  </div>
                  <span style={PS.keyBadge(p.api_key_set)}>
                    {p.api_key_set ? `Key: ${p.api_key_masked}` : 'No key'}
                  </span>
                  {!p.is_default && (
                    <button style={PS.actionBtn} onClick={() => handleSetDefault(p.id)}
                      title="Set as default">★</button>
                  )}
                  <button style={PS.actionBtn} onClick={() => {
                    setEditProvider(p)
                    setShowForm(true)
                  }} title="Edit provider">✎</button>
                  <button style={{ ...PS.actionBtn, color: 'var(--red)' }}
                    disabled={deleting === p.id}
                    onClick={() => handleDelete(p.id)}
                    title="Delete provider">
                    {deleting === p.id ? '…' : '✕'}
                  </button>
                </div>
              ))}
            </div>
            {!showForm && (
              <button style={{ ...PS.addBtn, marginTop: 12 }}
                onClick={() => { setEditProvider(null); setShowForm(true) }}>
                + Add Provider
              </button>
            )}
          </>
        )}
      </div>

      {showForm && (
        <ProviderForm
          provider={editProvider}
          onSave={handleFormDone}
          onCancel={() => { setShowForm(false); setEditProvider(null) }}
        />
      )}
    </>
  )
}
