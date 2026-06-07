import { useState, useEffect, useCallback } from 'react'
import { api, dispatchApiError, getReviewerId, setReviewerId } from '../api.js'
import {
  StatCard, DivBadge, PageHeader, EmptyState, SkeletonTable,
  pageStyle, tableStyles as T, statusBadge, hoverHandlers, filterChip,
} from './ui'

const S = {
  filterBar: { display:'flex', alignItems:'center', gap:10, marginBottom:20, flexWrap:'wrap' },
  idRow:    { display:'flex', alignItems:'center', gap:8,
              padding:'10px 14px', background:'var(--surface)', border:'1px solid var(--border)',
              borderRadius:8 },
  idLabel:  { fontSize:12, color:'var(--muted)', whiteSpace:'nowrap' },
  idInput:  { flex:1, background:'var(--surface2)', border:'1px solid var(--border)',
              borderRadius:5, color:'var(--text)', padding:'6px 10px', fontSize:12,
              fontFamily:'var(--font)', minWidth:140 },
  loadBtn:  { background:'var(--accent)', color:'var(--bg)', border:'none', borderRadius:5,
              padding:'6px 16px', fontSize:12, fontWeight:600, cursor:'pointer' },
  clearBtn: { background:'none', color:'var(--muted)', border:'1px solid var(--border)', borderRadius:5,
              padding:'6px 12px', fontSize:11, cursor:'pointer' },
  divChip:  (s) => ({
    fontWeight:700, fontSize:11,
    color: s < 0.2 ? 'var(--green)' : s < 0.5 ? 'var(--orange)' : 'var(--red)',
    background: s < 0.2 ? 'rgba(74,222,128,0.12)' : s < 0.5 ? 'rgba(251,191,36,0.12)' : 'rgba(248,113,113,0.12)',
    padding:'2px 8px', borderRadius:10, display:'inline-block',
  }),
  namePrompt: {
    background:'rgba(123,164,247,0.06)', border:'1px solid rgba(123,164,247,0.15)',
    borderRadius:8, padding:'14px 18px', marginBottom:20,
    display:'flex', alignItems:'center', gap:12, flexWrap:'wrap',
  },
  nameInput: {
    background:'var(--surface2)', border:'1px solid var(--border)',
    borderRadius:5, color:'var(--text)', padding:'6px 10px', fontSize:13,
    fontFamily:'var(--font)', minWidth:180,
  },
  saveNameBtn: {
    background:'var(--accent)', color:'var(--bg)', border:'none', borderRadius:5,
    padding:'6px 14px', fontSize:12, fontWeight:600, cursor:'pointer',
  },
  viewToggle: (active) => ({
    padding:'6px 14px', fontSize:12, fontWeight: active ? 600 : 400,
    color: active ? 'var(--bg)' : 'var(--muted)',
    background: active ? 'var(--accent)' : 'transparent',
    border: active ? 'none' : '1px solid var(--border)',
    borderRadius:5, cursor:'pointer',
  }),
}

export default function ReviewQueue({ nav }) {
  const [reviewerId, setRid]  = useState(() => getReviewerId())
  const [nameInput, setNameInput] = useState('')
  const [queue, setQueue]     = useState([])
  const [allPending, setAllPending] = useState([])
  const [loading, setLoading] = useState(true)
  const [view, setView]       = useState(() => getReviewerId() ? 'mine' : 'all')

  // Load all undecided comparisons (default view)
  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const comps = await api.listComparisons(null, true)
      setAllPending(comps || [])
    } catch (err) {
      dispatchApiError(err.message || 'Failed to load pending comparisons')
    } finally {
      setLoading(false)
    }
  }, [])

  // Load reviewer-specific queue
  const loadMine = useCallback(async () => {
    const rid = reviewerId.trim()
    if (!rid) return
    setLoading(true)
    try {
      const data = await api.getReviewQueue(rid)
      setQueue(data?.queue || data || [])
    } catch (err) {
      dispatchApiError(err.message || 'Failed to load review queue')
    } finally {
      setLoading(false)
    }
  }, [reviewerId])

  // Initial load
  useEffect(() => {
    if (view === 'all') {
      loadAll()
    } else if (reviewerId.trim()) {
      loadMine()
    } else {
      setLoading(false)
    }
  }, [view]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleSaveName() {
    const name = nameInput.trim()
    if (!name) return
    setRid(name)
    setReviewerId(name)
    setView('mine')
  }

  function handleViewChange(v) {
    setView(v)
    if (v === 'all') loadAll()
    else if (reviewerId.trim()) loadMine()
  }

  function handleIdChange(v) {
    setRid(v)
    setReviewerId(v)
  }

  // Determine which items to show
  const showItems = view === 'all' ? allPending : queue
  const pending    = view === 'all'
    ? allPending
    : queue.filter(q => q.status === 'pending')
  const inProgress = view === 'all' ? [] : queue.filter(q => q.status === 'in_progress')
  const completed  = view === 'all' ? [] : queue.filter(q => q.status === 'completed')
  const hasReviewer = !!reviewerId.trim()

  return (
    <div style={pageStyle(1100)}>
      <PageHeader
        title="Review Queue"
        subtitle={view === 'all'
          ? `${allPending.length} comparison${allPending.length !== 1 ? 's' : ''} waiting for a verdict`
          : `Comparisons assigned to ${reviewerId || 'you'}, sorted by divergence`}
      />

      {/* Name prompt for first-time users */}
      {!hasReviewer && view === 'all' && (
        <div style={S.namePrompt}>
          <span style={{ fontSize:13, color:'var(--text)' }}>
            What's your name? <span style={{ color:'var(--muted)', fontSize:12 }}>(Optional — used to track your reviews)</span>
          </span>
          <input
            style={S.nameInput}
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            placeholder="e.g. Sarah, QA Lead"
            onKeyDown={e => e.key === 'Enter' && handleSaveName()}
          />
          <button style={S.saveNameBtn} onClick={handleSaveName} disabled={!nameInput.trim()}>
            Save
          </button>
        </div>
      )}

      {/* View toggle + filter */}
      <div style={S.filterBar}>
        <button style={S.viewToggle(view === 'all')} onClick={() => handleViewChange('all')}>
          All Pending
        </button>
        <button style={S.viewToggle(view === 'mine')} onClick={() => handleViewChange('mine')}>
          My Assignments
        </button>

        {view === 'mine' && (
          <>
            <div style={{ width:1, height:20, background:'var(--border)', margin:'0 4px' }} />
            <input style={S.idInput} value={reviewerId} onChange={e => handleIdChange(e.target.value)}
                   placeholder="Your reviewer name or ID"
                   onKeyDown={e => e.key === 'Enter' && loadMine()} />
            <button style={S.loadBtn} onClick={loadMine} disabled={!reviewerId.trim()}>
              {loading ? 'Loading...' : 'Load'}
            </button>
          </>
        )}
      </div>

      {/* Stats (only for personal queue view) */}
      {view === 'mine' && queue.length > 0 && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20 }} data-layout="stats">
          <StatCard label="Pending"        value={pending.length} />
          <StatCard label="In Progress"    value={inProgress.length} />
          <StatCard label="Completed"      value={completed.length} color="var(--green)" />
          <StatCard label="Total Assigned" value={queue.length} />
        </div>
      )}

      {loading && <SkeletonTable rows={5} />}

      {!loading && showItems.length === 0 ? (
        <EmptyState
          body={view === 'mine' && !hasReviewer
            ? 'Enter your reviewer name above to load your personal queue, or switch to "All Pending" to see everything.'
            : view === 'mine'
              ? 'No assignments found for this reviewer. Switch to "All Pending" to see all undecided comparisons.'
              : 'No pending comparisons. Run a comparison from the sidebar to get started!'}
        />
      ) : !loading && (
        <table style={T.table}>
          <thead>
            <tr>
              <th style={T.th}>Comparison</th>
              <th style={T.th}>{view === 'all' ? 'Workflow' : 'Eval Run'}</th>
              <th style={T.th}>Divergence</th>
              {view === 'mine' && <th style={T.th}>Status</th>}
              <th style={T.th}>{view === 'all' ? 'Created' : 'Assigned'}</th>
            </tr>
          </thead>
          <tbody>
            {showItems
              .sort((a, b) => (b.divergence_score ?? 0) - (a.divergence_score ?? 0))
              .map(item => (
                <tr key={item.assignment_id || item.comparison_id || item.id} style={T.row}
                    onClick={() => nav('compare', {
                      compId: item.comparison_id || item.id,
                      evalRunId: item.eval_run_id
                    })}
                    {...hoverHandlers}
                >
                  <td style={T.td}>{item.test_case_label || `#${item.comparison_id || item.id}`}</td>
                  <td style={T.td}>
                    <span style={{ color:'var(--accent)' }}>
                      {view === 'all'
                        ? (item.workflow_name || '—')
                        : (item.eval_run_name || item.eval_run_id || '—')}
                    </span>
                  </td>
                  <td style={T.td}>
                    {(item.divergence_score != null)
                      ? <span style={S.divChip(item.divergence_score)}>{(item.divergence_score * 100).toFixed(0)}%</span>
                      : '—'}
                  </td>
                  {view === 'mine' && (
                    <td style={T.td}><span style={statusBadge(item.status)}>{item.status}</span></td>
                  )}
                  <td style={{ ...T.td, color:'var(--muted)', fontSize:11 }}>
                    {(item.assigned_at || item.created_at)
                      ? new Date(item.assigned_at || item.created_at).toLocaleDateString()
                      : '—'}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
