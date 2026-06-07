import { useState, useEffect } from 'react'
import { api } from '../api.js'
import {
  Modal, ModalFooter, ConfirmModal, EmptyState, PageHeader,
  SkeletonCard,
  pageStyle, statusBadge, formStyles as F, branchChip,
  hoverBorderHandlers, divColor, fmtDate,
} from './ui'

const S = {
  cards:  { display:'flex', flexDirection:'column', gap:10 },
  card: (status) => {
    const accentMap = { completed: 'var(--green)', running: 'var(--accent)', failed: 'var(--red)' }
    const accent = accentMap[status] || 'var(--border)'
    return {
      background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'2px 8px 8px 2px',
      borderLeft: `3px solid ${accent}`,
      padding:'16px 20px', cursor:'pointer', transition:'border-color 0.15s',
    }
  },
  cardH:  { display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:10 },
  name:   { fontSize:15, fontWeight:700, letterSpacing:'-0.02em' },
  desc:   { fontSize:12, color:'var(--muted)', marginTop:2 },
  branches:{ display:'flex', gap:8, marginTop:10, alignItems:'center', fontSize:12 },
  vs:     { color:'var(--muted)', fontSize:11 },
  progress: { marginTop:10 },
  pBar:   { height:4, background:'var(--border)', borderRadius:2, overflow:'hidden', marginBottom:4 },
  pFill:  (pct, color) => ({ height:'100%', width:`${pct}%`, background:color, borderRadius:2, transition:'width 0.3s' }),
  pLabel: { fontSize:11, color:'var(--muted)', display:'flex', justifyContent:'space-between' },
}

export default function EvalRuns({ nav }) {
  const [evalRuns,   setEvalRuns]   = useState([])
  const [workflows,  setWorkflows]  = useState([])
  const [showNew,    setShowNew]    = useState(false)
  const [loading,    setLoading]    = useState(true)
  const [deleteTarget, setDeleteTarget] = useState(null)

  async function load() {
    setLoading(true)
    const [ers, wfs] = await Promise.all([api.listEvalRuns(), api.listWorkflows()])
    setEvalRuns(ers)
    setWorkflows(wfs)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function deleteRun(id) {
    await api.deleteEvalRun(id)
    load()
  }

  return (
    <div style={pageStyle(1000)}>
      <PageHeader
        title="Eval Runs"
        subtitle="Batch evaluations comparing two branch configs across multiple test inputs"
        action={{ label: '+ New Eval Run', onClick: () => setShowNew(true) }}
      />

      {loading && <div style={{ display:'flex', flexDirection:'column', gap:10 }}>{[1,2,3].map(i => <SkeletonCard key={i} />)}</div>}

      {!loading && evalRuns.length === 0 && (
        <EmptyState
          heading="No eval runs yet"
          body="Create an eval run, then use the SDK to run your workflow across a batch of test inputs. Results appear here automatically as the SDK logs comparisons."
          action={{ label: '+ Create your first eval run', onClick: () => setShowNew(true) }}
        />
      )}

      <div style={S.cards}>
        {evalRuns.map(er => {
          const s     = er.stats || {}
          const total = er.total_cases || s.total || 0
          const done  = s.decided || 0
          const comp  = s.total   || 0
          const pct   = total > 0 ? Math.round((comp / total) * 100) : 0
          const dpct  = comp  > 0 ? Math.round((done / comp)  * 100) : 0

          return (
            <div key={er.id} style={S.card(er.status)}
                 onClick={() => nav('evalRunDetail', { evalRunId: er.id })}
                 {...hoverBorderHandlers}
            >
              <div style={S.cardH}>
                <div>
                  <div style={S.name}>{er.name}</div>
                  {er.description && <div style={S.desc}>{er.description}</div>}
                </div>
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  <span style={statusBadge(er.status)}>{er.status}</span>
                  <span style={{ fontSize:11, color:'var(--muted)' }}>{fmtDate(er.created_at)}</span>
                  <button style={{ fontSize:11, background:'none', border:'none', color:'var(--red)', cursor:'pointer', padding:'2px 6px' }}
                          onClick={e => { e.stopPropagation(); setDeleteTarget(er) }} aria-label={`Delete ${er.name}`}>✕</button>
                </div>
              </div>

              <div style={S.branches}>
                <span style={branchChip('A')}>{er.branch_a_config?.label || 'Branch A'}</span>
                <span style={S.vs}>vs</span>
                <span style={branchChip('B')}>{er.branch_b_config?.label || 'Branch B'}</span>
                {s.avg_divergence != null && (
                  <span style={{ marginLeft:'auto', fontSize:11, color: divColor(s.avg_divergence), fontWeight:600 }}>
                    avg Δ {(s.avg_divergence * 100).toFixed(0)}%
                  </span>
                )}
              </div>

              <div style={S.progress}>
                <div style={S.pBar}>
                  <div style={S.pFill(pct, 'var(--accent)')} />
                </div>
                <div style={S.pLabel}>
                  <span>{comp}/{total || '?'} comparisons logged</span>
                  <span style={{ color: dpct === 100 ? 'var(--green)' : 'var(--orange)' }}>
                    {done}/{comp} decided ({dpct}%)
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {showNew && (
        <NewEvalRunModal
          workflows={workflows}
          onClose={() => setShowNew(false)}
          onCreate={er => nav('evalRunDetail', { evalRunId: er.id })}
        />
      )}

      {deleteTarget && (
        <ConfirmModal
          title="Delete Eval Run"
          message={`Delete "${deleteTarget.name}" and all associated comparisons and decisions? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => deleteRun(deleteTarget.id)}
          onClose={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}

function NewEvalRunModal({ workflows, onClose, onCreate }) {
  const [wfName,    setWfName]   = useState(workflows[0]?.name || '')
  const [name,      setName]     = useState('')
  const [desc,      setDesc]     = useState('')
  const [aLabel,    setALabel]   = useState('Baseline')
  const [aModel,    setAModel]   = useState('gpt-4o-mini')
  const [aTemp,     setATemp]    = useState('0.3')
  const [bLabel,    setBLabel]   = useState('Challenger')
  const [bModel,    setBModel]   = useState('gpt-4o')
  const [bTemp,     setBTemp]    = useState('0.3')
  const [loading,   setLoading]  = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!name.trim() || !wfName.trim()) return
    setLoading(true)
    const er = await api.createEvalRun({
      workflow_name:   wfName.trim(),
      name:            name.trim(),
      description:     desc.trim(),
      branch_a_config: { label: aLabel, model_id: aModel, temperature: parseFloat(aTemp)||0.3 },
      branch_b_config: { label: bLabel, model_id: bModel, temperature: parseFloat(bTemp)||0.3 },
    })
    setLoading(false)
    onCreate(er)
    onClose()
  }

  return (
    <Modal onClose={onClose} width={520} title="New Eval Run"
           subtitle="Define two branch configs. Run your workflow with the SDK and open this eval run to review results.">
      <form onSubmit={submit}>
        <div style={{ marginBottom:18 }}>
          <label htmlFor="er-workflow" style={F.label}>Workflow *</label>
          <input id="er-workflow" style={F.input} value={wfName} onChange={e=>setWfName(e.target.value)}
            placeholder="Workflow name (will be created if new)" list="wf-list" />
          <datalist id="wf-list">
            {workflows.map(w => <option key={w.id} value={w.name} />)}
          </datalist>
          <label htmlFor="er-name" style={F.label}>Eval Run Name *</label>
          <input id="er-name" style={F.input} value={name} onChange={e=>setName(e.target.value)}
            placeholder="e.g. GPT-4o-mini vs GPT-4o — Q3 tickets" autoFocus />
          <label htmlFor="er-desc" style={F.label}>Description</label>
          <input id="er-desc" style={F.input} value={desc} onChange={e=>setDesc(e.target.value)}
            placeholder="Optional context" />
        </div>

        <div style={{ marginBottom:18 }}>
          <div style={{ fontSize:11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:8, display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ color:'var(--accent)' }}>■</span> Branch A (Baseline)
          </div>
          <div style={F.row2}>
            <div>
              <label htmlFor="er-a-label" style={F.label}>Label</label>
              <input id="er-a-label" style={F.input} value={aLabel} onChange={e=>setALabel(e.target.value)} />
            </div>
            <div>
              <label htmlFor="er-a-temp" style={F.label}>Temperature</label>
              <input id="er-a-temp" style={F.input} type="number" step="0.1" min="0" max="2"
                value={aTemp} onChange={e=>setATemp(e.target.value)} />
            </div>
          </div>
          <label htmlFor="er-a-model" style={F.label}>Model ID</label>
          <input id="er-a-model" style={F.input} value={aModel} onChange={e=>setAModel(e.target.value)}
            placeholder="e.g. gpt-4o-mini, claude-3-haiku-20240307" />
        </div>

        <div style={{ marginBottom:18 }}>
          <div style={{ fontSize:11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:8, display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ color:'var(--purple)' }}>■</span> Branch B (Challenger)
          </div>
          <div style={F.row2}>
            <div>
              <label htmlFor="er-b-label" style={F.label}>Label</label>
              <input id="er-b-label" style={F.input} value={bLabel} onChange={e=>setBLabel(e.target.value)} />
            </div>
            <div>
              <label htmlFor="er-b-temp" style={F.label}>Temperature</label>
              <input id="er-b-temp" style={F.input} type="number" step="0.1" min="0" max="2"
                value={bTemp} onChange={e=>setBTemp(e.target.value)} />
            </div>
          </div>
          <label htmlFor="er-b-model" style={F.label}>Model ID</label>
          <input id="er-b-model" style={F.input} value={bModel} onChange={e=>setBModel(e.target.value)}
            placeholder="e.g. gpt-4o, claude-3-5-sonnet-20241022" />
        </div>

        <div style={{ fontSize:11, color:'var(--muted)', marginBottom:16, padding:'10px 12px', background:'var(--surface2)', borderRadius:5, lineHeight:1.6 }}>
          After creating, run your workflow with:
          <code style={{ display:'block', marginTop:4, color:'var(--green)', fontFamily:'var(--mono)' }}>
            forkmark.eval_run(name="{name||'...'}", workflow="{wfName||'...'}", inputs=[...])
          </code>
        </div>

        <ModalFooter onCancel={onClose} submitLabel={loading ? 'Creating...' : 'Create Eval Run'}
                     disabled={loading||!name.trim()||!wfName.trim()} />
      </form>
    </Modal>
  )
}
