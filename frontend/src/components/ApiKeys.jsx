import { useState, useEffect } from 'react'
import { api, getActiveKey, setActiveKey, clearActiveKey } from '../api.js'
import {
  Modal, ModalFooter, ConfirmModal, EmptyState, PageHeader,
  pageStyle, panel, panelHeader, tableStyles as T,
  btnPrimary, btnDanger, formStyles as F,
  fmtDateLong,
} from './ui'

const S = {
  mono:    { fontFamily:'var(--mono)', fontSize:12, color:'var(--green)', background:'var(--surface2)', padding:'3px 8px', borderRadius:4 },
  date:    { color:'var(--muted)', fontSize:11 },
  useBtn:  { fontSize:11, padding:'4px 10px', background:'transparent', color:'var(--accent)', border:'1px solid var(--accent)', borderRadius:4, cursor:'pointer', marginRight:6 },
  activeChip: { fontSize:10, fontWeight:700, color:'var(--green)', background:'rgba(74,222,128,0.15)', padding:'2px 7px', borderRadius:8, marginLeft:8 },

  // active key banner
  banner:  { background:'rgba(74,222,128,0.08)', border:'1px solid rgba(74,222,128,0.25)', borderRadius:6, padding:'10px 14px', marginBottom:16, display:'flex', alignItems:'center', justifyContent:'space-between', fontSize:12 },
  bannerL: { color:'var(--green)', fontWeight:600 },
  bannerR: { color:'var(--muted)' },
  clearBtn:{ fontSize:11, padding:'3px 10px', background:'transparent', color:'var(--muted)', border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', marginLeft:12 },

  // raw key display
  rawBox:  { background:'var(--surface2)', border:'1px solid var(--green)', borderRadius:6, padding:14, marginBottom:16 },
  rawLabel:{ fontSize:11, color:'var(--green)', fontWeight:600, marginBottom:6 },
  rawKey:  { fontFamily:'var(--mono)', fontSize:13, color:'var(--text)', wordBreak:'break-all', userSelect:'all' },
  rawNote: { fontSize:11, color:'var(--orange)', marginTop:8 },
  copyBtn: { fontSize:11, padding:'4px 10px', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', color:'var(--text)', marginTop:8, marginRight:6 },
  activateBtn: { fontSize:11, padding:'4px 10px', background:'var(--green)', border:'none', borderRadius:4, cursor:'pointer', color:'var(--bg)', marginTop:8, fontWeight:600 },

  // activate-existing modal
  actHint: { fontSize:11, color:'var(--muted)', marginTop:4, marginBottom:12 },
}

function NewKeyModal({ onClose, onCreated }) {
  const [name,    setName]    = useState('')
  const [loading, setLoading] = useState(false)
  const [rawKey,  setRawKey]  = useState(null)
  const [copied,  setCopied]  = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    const res = await api.createKey({ name: name.trim() })
    setLoading(false)
    if (res?.raw_key) {
      setRawKey(res.raw_key)
      onCreated()
    }
  }

  function copy() {
    navigator.clipboard.writeText(rawKey).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  function activate() {
    setActiveKey(rawKey)
    onClose()
  }

  if (rawKey) {
    return (
      <Modal onClose={onClose} width={440} title="Key Created ✓" closable={false}>
        <div style={{ color:'var(--muted)', fontSize:12, marginBottom:16 }}>Copy this key now — it won't be shown again.</div>
        <div style={S.rawBox}>
          <div style={S.rawLabel}>Your API Key</div>
          <div style={S.rawKey}>{rawKey}</div>
          <div style={S.rawNote}>Store this securely. This is the only time it will be displayed.</div>
          <div style={{ marginTop:8 }}>
            <button style={S.copyBtn} onClick={copy}>
              {copied ? '✓ Copied!' : 'Copy'}
            </button>
            <button style={S.activateBtn} onClick={activate}>
              ✓ Use as active key
            </button>
          </div>
        </div>
        <div style={{ fontSize:11, color:'var(--muted)', marginBottom:16 }}>
          "Use as active key" saves it to your browser so the UI can authenticate write operations automatically.
        </div>
        <ModalFooter onSubmit={onClose} submitLabel="Done" />
      </Modal>
    )
  }

  return (
    <Modal onClose={onClose} width={440} title="Create API Key" subtitle="Used to authenticate SDK calls and UI write operations.">
      <form onSubmit={submit}>
        <label htmlFor="ak-name" style={F.label}>Key Name *</label>
        <input id="ak-name" style={F.input} value={name} onChange={e=>setName(e.target.value)}
          placeholder="e.g. Production, CI Pipeline, Dev Machine" autoFocus />
        <ModalFooter onCancel={onClose} onSubmit={submit} submitLabel="Create Key" loading={loading} disabled={!name.trim()} />
      </form>
    </Modal>
  )
}

/* ── Activate existing key modal ──────────────────────────────────────────── */
function ActivateKeyModal({ keyPrefix, onClose, onActivated }) {
  const [value,  setValue]  = useState('')
  const [error,  setError]  = useState('')

  function submit(e) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed.startsWith('fm_')) {
      setError('Key must start with fm_')
      return
    }
    if (!trimmed.startsWith(keyPrefix)) {
      setError(`Key does not match prefix ${keyPrefix}•••`)
      return
    }
    setActiveKey(trimmed)
    onActivated(trimmed)
    onClose()
  }

  return (
    <Modal onClose={onClose} width={440} title={<>Use Key <code style={{ fontFamily:'var(--mono)', fontSize:13 }}>{keyPrefix}•••</code></>}>
      <div style={{ color:'var(--muted)', fontSize:12, marginBottom:12 }}>
        Paste the full key to set it as your active key for UI write operations.
      </div>
      <form onSubmit={submit}>
        <label htmlFor="ak-full-key" style={F.label}>Full API Key *</label>
        <input
          id="ak-full-key"
          style={{ ...F.input, fontFamily:'var(--mono)' }}
          value={value}
          onChange={e => { setValue(e.target.value); setError('') }}
          placeholder={`${keyPrefix}...`}
          autoFocus
          spellCheck={false}
        />
        {error && <div style={{ fontSize:11, color:'var(--red)', marginTop:-8, marginBottom:10 }}>{error}</div>}
        <div style={S.actHint}>
          The key is stored only in your browser — it is never sent to the server except as an auth header.
        </div>
        <ModalFooter onCancel={onClose} onSubmit={submit} submitLabel="Activate" disabled={!value.trim()} />
      </form>
    </Modal>
  )
}

export default function ApiKeys() {
  const [keys,          setKeys]        = useState([])
  const [showNew,       setShowNew]     = useState(false)
  const [activateFor,   setActivateFor] = useState(null)
  const [activeKey,     setActive]      = useState(getActiveKey())
  const [revokeTarget,  setRevokeTarget]= useState(null) // { id, name }

  async function load() {
    const ks = await api.listKeys()
    setKeys(Array.isArray(ks) ? ks : [])
  }

  useEffect(() => { load() }, [])

  async function doRevoke() {
    if (!revokeTarget) return
    const k = keys.find(k => k.id === revokeTarget.id)
    if (k && activeKey.startsWith(k.key_prefix)) {
      clearActiveKey()
      setActive('')
    }
    await api.revokeKey(revokeTarget.id)
    setRevokeTarget(null)
    load()
  }

  function deactivate() {
    clearActiveKey()
    setActive('')
  }

  const activePrefix = activeKey ? activeKey.slice(0, 8) : null

  return (
    <div style={pageStyle(800)}>
      <PageHeader title="API Keys" subtitle={<>Keys authenticate SDK calls and UI write operations via the <code style={{ fontFamily:'var(--mono)', fontSize:11 }}>X-API-Key</code> header.</>} />

      {/* Active key banner */}
      {activeKey ? (
        <div style={S.banner}>
          <span style={S.bannerL}>✓ Active key: <code style={{ fontFamily:'var(--mono)' }}>{activeKey.slice(0,8)}•••</code></span>
          <span>
            <span style={S.bannerR}>Sent automatically on all write requests</span>
            <button style={S.clearBtn} onClick={deactivate}>Clear</button>
          </span>
        </div>
      ) : (
        <div style={{ ...S.banner, background:'rgba(251,191,36,0.08)', borderColor:'rgba(251,191,36,0.25)', marginBottom:16 }}>
          <span style={{ color:'var(--orange)', fontWeight:600, fontSize:12 }}>No active key — create one and click "Use as active key"</span>
        </div>
      )}

      <div style={panel}>
        <div style={panelHeader}>
          <span>Keys ({keys.length})</span>
          <button style={{ ...btnPrimary, fontSize:12, padding:'5px 12px' }} onClick={() => setShowNew(true)}>+ New Key</button>
        </div>

        {keys.length === 0
          ? <EmptyState heading="No API keys" body="Create one to start using the SDK." />
          : (
            <table style={T.table}>
              <thead>
                <tr>
                  <th style={T.th}>Name</th>
                  <th style={T.th}>Prefix</th>
                  <th style={T.th}>Created</th>
                  <th style={T.th}>Last Used</th>
                  <th style={T.th}></th>
                </tr>
              </thead>
              <tbody>
                {keys.map(k => {
                  const isActive = activePrefix && activePrefix === k.key_prefix
                  return (
                    <tr key={k.id}>
                      <td style={T.td}>
                        {k.name}
                        {isActive && <span style={S.activeChip}>ACTIVE</span>}
                      </td>
                      <td style={T.td}><span style={S.mono}>{k.key_prefix}•••••••</span></td>
                      <td style={{ ...T.td, ...S.date }}>{fmtDateLong(k.created_at)}</td>
                      <td style={{ ...T.td, ...S.date }}>{fmtDateLong(k.last_used_at)}</td>
                      <td style={T.td}>
                        {!isActive && (
                          <button style={S.useBtn} onClick={() => setActivateFor(k.key_prefix)}>
                            Use
                          </button>
                        )}
                        <button style={btnDanger} onClick={() => setRevokeTarget({ id: k.id, name: k.name })}>Revoke</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )
        }
      </div>

      <div style={panel}>
        <div style={panelHeader}><span>Quick Start</span></div>
        <div style={{ padding:'14px 16px', fontSize:12 }}>
          <div style={{ marginBottom:10, color:'var(--muted)' }}>Install the SDK:</div>
          <pre style={{ background:'var(--surface2)', padding:'10px 14px', borderRadius:6, fontSize:12, color:'var(--green)', margin:'0 0 16px' }}>pip install forkmark</pre>
          <div style={{ marginBottom:10, color:'var(--muted)' }}>Initialize and run:</div>
          <pre style={{ background:'var(--surface2)', padding:'10px 14px', borderRadius:6, fontSize:12, color:'var(--text)', margin:'0 0 16px', lineHeight:1.7 }}>{`import forkmark

forkmark.init(api_key="fm_your_key_here")

with forkmark.run("My Workflow") as wf:
    # baseline branch (A)
    # call_fn can return str OR (str, tokens_in, tokens_out)
    result_a = wf.step(
        "summarize",
        model="gpt-4o-mini",
        messages=[{"role":"user","content":doc}],
        call_fn=lambda msgs, model, temp: my_openai_call(msgs, model, temp)
    )
    # challenger branch (B)
    result_b = wf.branch_step(
        "summarize",
        model="gpt-4o",
        messages=[{"role":"user","content":doc}],
        call_fn=lambda msgs, model, temp: my_openai_call(msgs, model, temp)
    )
# comparison auto-created — review it in the UI`}</pre>
          <div style={{ marginBottom:10, color:'var(--muted)' }}>Parallel batch eval (4-10x faster):</div>
          <pre style={{ background:'var(--surface2)', padding:'10px 14px', borderRadius:6, fontSize:12, color:'var(--text)', margin:0, lineHeight:1.7 }}>{`with forkmark.eval_run(
    name="my eval",
    workflow="my-workflow",
    branch_a={"label": "mini", "model_id": "gpt-4o-mini"},
    branch_b={"label": "4o",   "model_id": "gpt-4o"},
    inputs=test_cases,
) as er:
    def process(case):
        case.step("answer", model="gpt-4o-mini", messages=[...], call_fn=fn)
        case.branch_step("answer", model="gpt-4o", messages=[...], call_fn=fn)

    er.run(process, max_workers=8)  # parallel execution`}</pre>
        </div>
      </div>

      {showNew && (
        <NewKeyModal
          onClose={() => { setShowNew(false); setActive(getActiveKey()) }}
          onCreated={() => load()}
        />
      )}

      {activateFor && (
        <ActivateKeyModal
          keyPrefix={activateFor}
          onClose={() => setActivateFor(null)}
          onActivated={(full) => setActive(full)}
        />
      )}

      {revokeTarget && (
        <ConfirmModal
          title="Revoke API Key"
          message={`Revoke key "${revokeTarget.name}"? This cannot be undone.`}
          confirmLabel="Revoke"
          variant="danger"
          onConfirm={doRevoke}
          onClose={() => setRevokeTarget(null)}
        />
      )}
    </div>
  )
}
