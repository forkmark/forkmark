import { useState, useEffect } from 'react'
import { api } from '../api.js'
import {
  Modal, ModalFooter, ConfirmModal, EmptyState, PageHeader, SkeletonCard,
  pageStyle, formStyles as F, btnDanger,
} from './ui'

const S = {
  sets:    { display:'flex', flexDirection:'column', gap:10 },
  set:     { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8 },
  setH:    { display:'flex', alignItems:'center', justifyContent:'space-between', padding:'14px 16px', cursor:'pointer' },
  setName: { fontWeight:600, fontSize:14 },
  setMeta: { fontSize:11, color:'var(--muted)', marginTop:2 },
  badge:   { fontSize:11, background:'var(--surface2)', color:'var(--muted)', padding:'2px 8px', borderRadius:10, marginLeft:8 },
  chevron: (open) => ({ fontSize:12, color:'var(--muted)', transform: open ? 'rotate(90deg)' : '', transition:'transform 0.15s' }),
  actions: { display:'flex', gap:8 },
  casesWrap:{ borderTop:'1px solid var(--border)', padding:'12px 16px' },
  caseRow: { display:'flex', alignItems:'center', gap:10, padding:'7px 0', borderBottom:'1px solid var(--border)', fontSize:13 },
  cLabel:  { flex:1, fontWeight:500 },
  cData:   { fontSize:11, color:'var(--muted)', maxWidth:280, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' },
  cDel:    { fontSize:11, background:'none', border:'none', color:'var(--red)', cursor:'pointer', padding:'2px 6px' },
  addForm: { display:'flex', gap:8, marginTop:10 },
  input:   { background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, color:'var(--text)', padding:'7px 10px', fontSize:12, fontFamily:'var(--font)', flex:1 },
  addBtn:  { fontSize:12, padding:'7px 14px', background:'var(--surface2)', color:'var(--text)', border:'1px solid var(--border)', borderRadius:5, cursor:'pointer', whiteSpace:'nowrap' },
  bulkArea:{ width:'100%', background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, color:'var(--text)', padding:'8px 10px', fontSize:12, fontFamily:'var(--mono)', resize:'vertical', minHeight:80, marginTop:8, boxSizing:'border-box' },
  bulkNote:{ fontSize:11, color:'var(--muted)', marginTop:4 },
  bulkBtn: { fontSize:12, padding:'6px 12px', background:'var(--surface)', color:'var(--text)', border:'1px solid var(--border)', borderRadius:5, cursor:'pointer', marginTop:6 },
}

function TestSetPanel({ ts, onDeleted }) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [open,        setOpen]        = useState(false)
  const [cases,       setCases]       = useState([])
  const [label,       setLabel]       = useState('')
  const [payload,     setPayload]     = useState('')
  const [showMeta,    setShowMeta]    = useState(false)
  const [metaDomain,  setMetaDomain]  = useState('')
  const [metaIndustry,setMetaIndustry]= useState('')
  const [metaUseCase, setMetaUseCase] = useState('')
  const [metaFailure, setMetaFailure] = useState('')
  const [metaGoal,    setMetaGoal]    = useState('')
  const [bulk,        setBulk]        = useState('')
  const [bulkError,   setBulkError]   = useState('')

  async function loadCases() {
    const data = await api.getTestSet(ts.id)
    setCases(data.cases || [])
  }

  function toggle() {
    if (!open) loadCases()
    setOpen(v => !v)
  }

  async function addCase() {
    if (!label.trim()) return
    let inputData = {}
    try { inputData = payload.trim() ? JSON.parse(payload) : {} } catch { inputData = { text: payload } }
    const tc = await api.addTestCase(ts.id, { label: label.trim(), input_data: inputData })
    if (tc?.id && (metaDomain || metaIndustry || metaUseCase || metaFailure || metaGoal)) {
      await api.patchTestCaseMetadata(ts.id, tc.id, {
        domain: metaDomain, industry: metaIndustry,
        use_case_type: metaUseCase, failure_mode: metaFailure, test_goal: metaGoal,
      }).catch(() => {})
    }
    setLabel(''); setPayload('')
    setMetaDomain(''); setMetaIndustry(''); setMetaUseCase(''); setMetaFailure(''); setMetaGoal('')
    loadCases()
  }

  async function addBulk() {
    setBulkError('')
    try {
      const lines = bulk.trim().split('\n').filter(Boolean)
      const cases = lines.map((line, i) => {
        try {
          const parsed = JSON.parse(line)
          return { label: parsed.label || `case-${i+1}`, input_data: parsed }
        } catch {
          return { label: `case-${i+1}`, input_data: { text: line } }
        }
      })
      await api.bulkAddTestCases(ts.id, cases)
      setBulk('')
      loadCases()
    } catch(e) {
      setBulkError('Import failed: ' + (e?.message || 'unknown error'))
    }
  }

  async function deleteCase(tcId) {
    await api.deleteTestCase(ts.id, tcId)
    loadCases()
  }

  async function deleteSet() {
    await api.deleteTestSet(ts.id)
    setShowDeleteConfirm(false)
    onDeleted()
  }

  return (
    <div style={S.set}>
      <div style={S.setH} onClick={toggle}>
        <div>
          <div style={{ display:'flex', alignItems:'center' }}>
            <span style={S.setName}>{ts.name}</span>
            <span style={S.badge}>{ts.case_count} cases</span>
          </div>
          {ts.description && <div style={S.setMeta}>{ts.description}</div>}
        </div>
        <div style={S.actions} onClick={e=>e.stopPropagation()}>
          <button style={btnDanger} onClick={() => setShowDeleteConfirm(true)}>Delete</button>
          <span style={S.chevron(open)}>▶</span>
        </div>
      </div>

      {open && (
        <div style={S.casesWrap}>
          {cases.length === 0 && (
            <div style={{ color:'var(--muted)', fontSize:12, marginBottom:10 }}>No cases yet. Add some below.</div>
          )}
          {cases.map(c => (
            <div key={c.id} style={S.caseRow}>
              <span style={S.cLabel}>{c.label}</span>
              <span style={S.cData}>{JSON.stringify(c.input_data)}</span>
              <button style={S.cDel} onClick={() => deleteCase(c.id)} aria-label={`Delete case ${c.label || c.id}`}>✕</button>
            </div>
          ))}

          <div style={{ marginTop:12 }}>
            <div style={{ fontSize:11, color:'var(--muted)', marginBottom:6 }}>Add single case</div>
            <div style={S.addForm}>
              <input style={S.input} value={label} onChange={e=>setLabel(e.target.value)} placeholder="Label" />
              <input style={S.input} value={payload} onChange={e=>setPayload(e.target.value)} placeholder='JSON payload or plain text' />
              <button style={S.addBtn} onClick={addCase} disabled={!label.trim()}>Add</button>
            </div>
            <div style={{ marginTop:6 }}>
              <button
                style={{ fontSize:11, background:'none', border:'none', color:'var(--muted)', cursor:'pointer', padding:0, textDecoration:'underline' }}
                onClick={() => setShowMeta(v => !v)}
              >
                {showMeta ? '▾ Hide metadata' : '▸ Add domain metadata (flywheel)'}
              </button>
              {showMeta && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginTop:8 }}>
                  <input style={S.input} value={metaDomain}   onChange={e=>setMetaDomain(e.target.value)}   placeholder="Domain (e.g. customer-support)" />
                  <input style={S.input} value={metaIndustry} onChange={e=>setMetaIndustry(e.target.value)} placeholder="Industry (e.g. e-commerce)" />
                  <input style={S.input} value={metaUseCase}  onChange={e=>setMetaUseCase(e.target.value)}  placeholder="Use case type (e.g. complaint)" />
                  <input style={S.input} value={metaFailure}  onChange={e=>setMetaFailure(e.target.value)}  placeholder="Failure mode (e.g. refusal)" />
                  <input style={{ ...S.input, gridColumn:'span 2' }} value={metaGoal} onChange={e=>setMetaGoal(e.target.value)} placeholder="Test goal (e.g. check empathy)" />
                </div>
              )}
            </div>
          </div>

          <div style={{ marginTop:14 }}>
            <div style={{ fontSize:11, color:'var(--muted)', marginBottom:4 }}>Bulk import (one per line)</div>
            <textarea style={S.bulkArea} value={bulk} onChange={e=>setBulk(e.target.value)}
              placeholder={'{"label": "ticket-1", "text": "My order is late"}\n{"label": "ticket-2", "text": "Wrong item shipped"}'}
            />
            <div style={S.bulkNote}>JSON objects with a "label" key, or plain text lines. One per line.</div>
            {bulkError && <div style={{ fontSize:11, color:'var(--red)', marginTop:4, marginBottom:4 }}>{bulkError}</div>}
            <button style={S.bulkBtn} onClick={addBulk} disabled={!bulk.trim()}>
              Import {bulk.trim().split('\n').filter(Boolean).length} cases
            </button>
          </div>
        </div>
      )}
      {showDeleteConfirm && (
        <ConfirmModal
          title="Delete Test Set"
          message={`Delete test set "${ts.name}" and all its cases? This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={deleteSet}
          onClose={() => setShowDeleteConfirm(false)}
        />
      )}
    </div>
  )
}

export default function TestSets({ nav }) {
  const [sets,    setSets]    = useState([])
  const [showNew, setShowNew] = useState(false)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    setSets(await api.listTestSets())
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  return (
    <div style={pageStyle(900)}>
      <PageHeader
        title="Test Sets"
        subtitle="Named collections of test inputs. Reference them when creating eval runs."
        action={{ label: '+ New Test Set', onClick: () => setShowNew(true) }}
      />

      {loading && <div style={{ display:'flex', flexDirection:'column', gap:10 }}>{[1,2,3].map(i => <SkeletonCard key={i} />)}</div>}

      {!loading && sets.length === 0 && (
        <EmptyState body="No test sets yet. Create one to start organizing your eval inputs." />
      )}

      <div style={S.sets}>
        {sets.map(ts => (
          <TestSetPanel key={ts.id} ts={ts} onDeleted={load} />
        ))}
      </div>

      {showNew && (
        <NewSetModal onClose={() => setShowNew(false)} onCreate={() => { load(); setShowNew(false) }} />
      )}
    </div>
  )
}

function NewSetModal({ onClose, onCreate }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    await api.createTestSet({ name: name.trim(), description: desc.trim() })
    setLoading(false)
    onCreate()
  }

  return (
    <Modal onClose={onClose} title="New Test Set">
      <form onSubmit={submit}>
        <label htmlFor="ts-name" style={F.label}>Name *</label>
        <input id="ts-name" style={F.input} value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Q3 support tickets" autoFocus />
        <label htmlFor="ts-desc" style={F.label}>Description</label>
        <input id="ts-desc" style={F.input} value={desc} onChange={e=>setDesc(e.target.value)} placeholder="Optional" />
        <ModalFooter onCancel={onClose} submitLabel={loading ? '...' : 'Create'} disabled={loading||!name.trim()} />
      </form>
    </Modal>
  )
}
