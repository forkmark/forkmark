import { useState, useEffect } from 'react'
import { api } from '../api.js'
import {
  ConfirmModal, DivBadge, EmptyState,
  pageStyle, panel, panelHeader, tableStyles as T, statusBadge,
  hoverHandlers, btnDanger, fmtDateTime,
} from './ui'

const S = {
  head:   { display:'flex', alignItems:'center', gap:12, marginBottom:4 },
  back:   { background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:13, padding:0 },
  h1:     { fontSize:20, fontWeight:700 },
  muted:  { color:'var(--muted)', fontSize:13, marginBottom:24 },
  panels: { display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 },
  decided:{ color:'var(--green)', fontSize:11 },
  pending:{ color:'var(--orange)', fontSize:11 },
  histBtn:{ fontSize:12, padding:'5px 12px', background:'transparent', color:'var(--accent)', border:'1px solid var(--accent)', borderRadius:5, cursor:'pointer' },
}

export default function WorkflowDetail({ workflowId, nav }) {
  const [runs,       setRuns]       = useState([])
  const [comps,      setComps]      = useState([])
  const [wf,         setWf]         = useState(null)
  const [tab,        setTab]        = useState('comparisons')
  const [showDelete, setShowDelete] = useState(false)

  useEffect(() => {
    if (!workflowId) return
    load()
  }, [workflowId])

  async function load() {
    const [wf, rs, cs] = await Promise.all([
      api.getWorkflow(workflowId),
      api.listRuns(workflowId),
      api.listComparisons(workflowId),
    ])
    setWf(wf)
    setRuns(rs)
    setComps(cs)
  }

  async function deleteWorkflow() {
    await api.deleteWorkflow(workflowId)
    nav('dashboard')
  }

  const tabBtn = (id, label) => ({
    background: tab===id ? 'var(--accent)' : 'transparent',
    color:      tab===id ? 'var(--bg)' : 'var(--muted)',
    border:     '1px solid ' + (tab===id ? 'var(--accent)' : 'var(--border)'),
    borderRadius:5, padding:'5px 14px', fontSize:12, fontWeight:600, cursor:'pointer',
  })

  if (!workflowId) return <div style={{ padding:24, color:'var(--muted)' }}>Select a workflow</div>

  return (
    <div style={pageStyle()}>
      <div style={S.head}>
        <button style={S.back} onClick={() => nav('dashboard')}>← Back</button>
        <div style={S.h1}>{wf?.name ?? 'Workflow'}</div>
      </div>
      <div style={{ ...S.muted, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <span>{wf?.description || 'No description'} · {runs.length} runs · {wf?.decision_count ?? 0} decisions</span>
        <div style={{ display:'flex', gap:8 }}>
          <button style={S.histBtn} onClick={() => nav('history', { workflowId })}>Decision History</button>
          <button style={btnDanger} onClick={() => setShowDelete(true)}>Delete</button>
        </div>
      </div>

      <div style={{ display:'flex', gap:8, marginBottom:16 }}>
        <button style={tabBtn('comparisons','Comparisons')} onClick={() => setTab('comparisons')}>
          Comparisons ({comps.length})
        </button>
        <button style={tabBtn('runs','Runs')} onClick={() => setTab('runs')}>
          Runs ({runs.length})
        </button>
      </div>

      <div style={panel}>
        {tab === 'comparisons' && (
          <>
            <div style={panelHeader}>
              <span>Branch Comparisons</span>
              <span style={{ fontSize:11, color:'var(--muted)' }}>
                {comps.filter(c=>c.decided).length}/{comps.length} decided
              </span>
            </div>
            {comps.length === 0
              ? <EmptyState heading="No comparisons yet" body="Run the SDK to generate comparisons." />
              : (
                <table style={T.table}>
                  <thead>
                    <tr>
                      <th style={T.th}>ID</th>
                      <th style={T.th}>Run</th>
                      <th style={T.th}>Branches</th>
                      <th style={T.th}>Divergence</th>
                      <th style={T.th}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comps.map(c => (
                      <tr key={c.id} style={T.row}
                          onClick={() => nav('compare', { compId: c.id })}
                          role="link" tabIndex={0}
                          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); nav('compare', { compId: c.id }) } }}
                          {...hoverHandlers}
                      >
                        <td style={T.td}>#{c.id}</td>
                        <td style={{ ...T.td, color:'var(--muted)', fontSize:12 }}>Run #{c.run_id}</td>
                        <td style={T.td}>
                          <span style={{ color:'var(--accent)' }}>A</span>
                          {' vs '}
                          <span style={{ color:'var(--purple)' }}>B</span>
                        </td>
                        <td style={T.td}><DivBadge score={c.divergence_score} /></td>
                        <td style={T.td}>
                          {c.decided
                            ? <span style={S.decided}>✓ Decided</span>
                            : <span style={S.pending}>Pending</span>
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            }
          </>
        )}

        {tab === 'runs' && (
          <>
            <div style={panelHeader}><span>Workflow Runs</span></div>
            {runs.length === 0
              ? <EmptyState heading="No runs yet" body="Use the SDK or Workflow Builder to trigger a run." />
              : (
                <table style={T.table}>
                  <thead>
                    <tr>
                      <th style={T.th}>Run ID</th>
                      <th style={T.th}>Status</th>
                      <th style={T.th}>Started</th>
                      <th style={T.th}>Completed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(r => (
                      <tr key={r.id} style={{ fontSize:13 }}>
                        <td style={T.td}>#{r.id}</td>
                        <td style={T.td}><span style={statusBadge(r.status)}>{r.status}</span></td>
                        <td style={{ ...T.td, color:'var(--muted)' }}>{fmtDateTime(r.created_at)}</td>
                        <td style={{ ...T.td, color:'var(--muted)' }}>{fmtDateTime(r.completed_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            }
          </>
        )}
      </div>

      {showDelete && (
        <ConfirmModal
          title="Delete Workflow"
          message={`Delete "${wf?.name}" and all runs, comparisons, and decisions? This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={deleteWorkflow}
          onClose={() => setShowDelete(false)}
        />
      )}
    </div>
  )
}
