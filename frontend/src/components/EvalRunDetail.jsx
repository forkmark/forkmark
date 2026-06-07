import { useState, useEffect, useCallback } from 'react'
import { api, dispatchApiError } from '../api.js'
import {
  StatCard, DivBadge, PageHeader, SkeletonStatCards, Breadcrumb,
  DivergenceDotPlot,
  pageStyle, statusBadge, tableStyles as T, filterChip,
  hoverHandlers, divColor, divBg, choiceColor, choiceBg,
  branchCost,
} from './ui'

const BUCKET_LABELS = ['0–20%', '20–40%', '40–60%', '60–80%', '80–100%']
const BUCKET_COLORS = ['#4ade80', '#6ec99e', '#e5a73d', '#d98b52', '#f87171']

const S = {
  back:    { background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:13, padding:0 },
  meta:    { color:'var(--muted)', fontSize:13, marginBottom:20, display:'flex', gap:16, alignItems:'center', flexWrap:'wrap' },
  statsRow:{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:10, marginBottom:20 },
  branches:{ display:'flex', gap:12, marginBottom:20 },
  bCard:   (side) => ({
    flex:1, background:'var(--surface)',
    border:'1px solid var(--border)',
    borderLeft: `3px solid ${side === 'A' ? 'var(--accent)' : side === 'B' ? 'var(--purple)' : 'var(--border)'}`,
    borderRadius:'2px 8px 8px 2px', padding:'12px 14px',
  }),
  bSide:   (side) => ({ fontSize:10, fontWeight:600, color: side === 'A' ? 'var(--accent)' : side === 'B' ? 'var(--purple)' : 'var(--muted)', marginBottom:4, textTransform:'uppercase', letterSpacing:'0.08em' }),
  bLabel:  { fontSize:13, fontWeight:700, letterSpacing:'-0.01em' },
  bMeta:   { fontSize:11, color:'var(--muted)', marginTop:3 },
  histPanel:{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:'16px', marginBottom:20 },
  histH:   { fontSize:12, fontWeight:600, marginBottom:12 },
  histRow: { display:'flex', alignItems:'flex-end', gap:6, height:60 },
  histBar: (pct, color) => ({
    flex:1, background:color, borderRadius:'3px 3px 0 0',
    height:`${Math.max(pct * 100, pct > 0 ? 4 : 0)}%`,
    display:'flex', alignItems:'flex-end', justifyContent:'center',
    paddingBottom:2, fontSize:10, color:'var(--bg)', fontWeight:700,
    transition:'height 0.3s', minHeight: pct > 0 ? 16 : 0,
  }),
  histLabels:{ display:'flex', gap:6, marginTop:4 },
  histLbl:  { flex:1, fontSize:10, color:'var(--muted)', textAlign:'center' },
  histLegend:{ display:'flex', gap:16, marginTop:8, fontSize:11, color:'var(--muted)' },
  toolbar: { display:'flex', gap:10, alignItems:'center', marginBottom:12, flexWrap:'wrap' },
  searchBox:{ background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, color:'var(--text)', padding:'5px 10px', fontSize:12, fontFamily:'var(--font)', minWidth:180 },
  threshGroup:{ display:'flex', alignItems:'center', gap:8, padding:'4px 10px', background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5 },
  threshLabel:{ fontSize:11, color:'var(--muted)', whiteSpace:'nowrap' },
  threshVal:{ fontSize:12, fontWeight:700, color:'var(--accent)', minWidth:34, textAlign:'right' },
  threshNote:{ fontSize:12, color:'var(--muted)', marginBottom:12 },
  reviewNext:{ fontSize:12, padding:'6px 14px', background:'var(--accent)', color:'var(--bg)', border:'none', borderRadius:5, fontWeight:700, cursor:'pointer', marginLeft:'auto' },
  exportBtn: { fontSize:12, padding:'6px 14px', background:'transparent', color:'var(--green)', border:'1px solid var(--green)', borderRadius:5, cursor:'pointer', fontWeight:600 },
  dpoBtn: { fontSize:12, padding:'6px 14px', background:'linear-gradient(135deg, var(--purple) 0%, var(--accent) 100%)', color:'#fff', border:'none', borderRadius:5, cursor:'pointer', fontWeight:700, letterSpacing:'0.3px' },
  exportDropdown: { position:'relative', display:'inline-block' },
  exportMenu: { position:'absolute', top:'100%', right:0, marginTop:4, background:'var(--surface)', border:'1px solid var(--border)', borderRadius:6, padding:'4px 0', minWidth:200, zIndex:100, boxShadow:'0 8px 24px rgba(0,0,0,0.4)' },
  exportMenuItem: { display:'block', width:'100%', padding:'8px 14px', background:'none', border:'none', color:'var(--text)', fontSize:12, textAlign:'left', cursor:'pointer', fontFamily:'var(--font)' },
  panel:   { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8 },
  divChip: (s) => ({
    fontWeight:700, fontSize:11,
    color: divColor(s), background: divBg(s),
    padding:'2px 8px', borderRadius:8, display:'inline-block',
  }),
  choiceChip:(c) => ({
    fontSize:11, fontWeight:700, color: choiceColor(c), background: choiceBg(c),
    padding:'2px 8px', borderRadius:8, display:'inline-block',
  }),
  empty:   { padding:32, color:'var(--muted)', textAlign:'center', fontSize:13 },
  noData:  { color:'var(--muted)', fontStyle:'italic' },
}

export default function EvalRunDetail({ evalRunId, nav }) {
  const [er,      setEr]      = useState(null)
  const [filter,  setFilter]  = useState('all')
  const [search,  setSearch]  = useState('')
  const [minDiv,  setMinDiv]  = useState(0)   // review-threshold (0–1); 0 = show all
  const [loading, setLoading] = useState(true)
  const [showExportMenu, setShowExportMenu] = useState(false)

  const load = useCallback(async () => {
    if (!evalRunId) return
    setLoading(true)
    try {
      const data = await api.getEvalRun(evalRunId)
      setEr(data)
    } catch (err) {
      dispatchApiError(err.message || 'Failed to load eval run')
    } finally {
      setLoading(false)
    }
  }, [evalRunId])

  useEffect(() => { load() }, [load])

  if (!evalRunId) return <div style={{ padding:24, color:'var(--muted)' }}>No eval run selected</div>
  if (loading)   return <div style={pageStyle(1200)}><SkeletonStatCards count={5} /></div>
  if (!er)       return <div style={{ padding:24, color:'var(--red)' }}>Eval run not found</div>

  const stats   = er.stats || {}
  const comps   = stats.comparisons || []
  const buckets = stats.divergence_buckets || [0,0,0,0,0]
  const maxBuck = Math.max(...buckets, 1)

  const modelA   = er.branch_a_config?.model_id
  const modelB   = er.branch_b_config?.model_id
  const costUsdA = branchCost(stats.tokens_a, stats.tokens_a_out, modelA)
  const costUsdB = branchCost(stats.tokens_b, stats.tokens_b_out, modelB)
  const hasCost  = costUsdA != null || costUsdB != null

  const searchLower = search.toLowerCase()
  const filtered = comps.filter(c => {
    if (filter === 'undecided' && c.decided) return false
    if (filter === 'high' && (c.divergence_score || 0) < 0.5) return false
    if (minDiv > 0 && (c.divergence_score || 0) < minDiv) return false
    if (search && !((c.test_case_label || '').toLowerCase().includes(searchLower))) return false
    return true
  })

  // Cases at/above the review threshold that still need a verdict.
  const needsReview = comps.filter(c => !c.decided && (c.divergence_score || 0) >= minDiv)
  const aboveThresh = comps.filter(c => (c.divergence_score || 0) >= minDiv).length
  const nextUndecided = needsReview[0]
  const totalStr  = er.total_cases || stats.total || '?'
  const compCount = stats.total    || 0
  const decided   = stats.decided  || 0
  const pending   = stats.pending  || compCount - decided

  function openComparison(compId) {
    nav('compare', { compId, evalRunId: er.id })
  }

  return (
    <div style={pageStyle(1200)}>
      <Breadcrumb items={[
        { label: 'Results', onClick: () => nav('evalRuns') },
        { label: er.name },
      ]} />
      <PageHeader
        title={er.name}
        right={<span style={statusBadge(er.status)}>{er.status}</span>}
      />
      <div style={S.meta}>
        {er.description && <span>{er.description}</span>}
        <span>{compCount} comparisons · {totalStr} inputs</span>
        <span style={{ fontSize:11, color:'var(--muted)' }}>{er.created_at?.split('T')[0]}</span>
      </div>

      {/* Branch config cards */}
      <div style={S.branches}>
        {[['A', er.branch_a_config], ['B', er.branch_b_config]].map(([side, cfg]) => (
          <div key={side} style={S.bCard(side)}>
            <div style={S.bSide(side)}>Branch {side}</div>
            <div style={S.bLabel}>{cfg?.label || `Branch ${side}`}</div>
            <div style={S.bMeta}>
              {cfg?.model_id && <span>{cfg.model_id}</span>}
              {cfg?.temperature != null && <span> · temp {cfg.temperature}</span>}
              {cfg?.system_prompt && <span> · custom prompt</span>}
              {cfg?.provider_id && <span style={{ marginLeft:4, fontSize:10, padding:'1px 5px', borderRadius:3, background:'rgba(196,161,245,0.12)', color:'var(--purple)' }}>via provider</span>}
            </div>
          </div>
        ))}
        <div style={{ ...S.bCard(''), flex:'none', minWidth:140, textAlign:'center', border:'1px solid var(--border)' }}>
          <div style={{ ...S.bSide(''), color:'var(--muted)' }}>AVG DIVERGENCE</div>
          {stats.avg_divergence != null
            ? <div style={{ fontSize:28, fontWeight:700, color: divColor(stats.avg_divergence) }}>
                {(stats.avg_divergence * 100).toFixed(0)}%
              </div>
            : <div style={{ fontSize:14, color:'var(--muted)', marginTop:8 }}>—</div>
          }
        </div>
        {hasCost && (
          <div style={{ ...S.bCard(''), flex:'none', minWidth:160, border:'1px solid var(--border)' }}>
            <div style={{ ...S.bSide(''), color:'var(--muted)' }}>EST. COST</div>
            {['A','B'].map(side => {
              const cost = side === 'A' ? costUsdA : costUsdB
              const tokIn  = side === 'A' ? stats.tokens_a     : stats.tokens_b
              const tokOut = side === 'A' ? stats.tokens_a_out : stats.tokens_b_out
              return (
                <div key={side} style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginTop:4 }}>
                  <span style={{ fontSize:11, fontWeight:700, color: side === 'A' ? 'var(--accent)' : 'var(--purple)' }}>{side}</span>
                  <span style={{ fontSize:13, fontWeight:700 }}>{cost != null ? `~$${cost.toFixed(4)}` : '—'}</span>
                  <span style={{ fontSize:10, color:'var(--muted)' }}>{((tokIn||0)+(tokOut||0)).toLocaleString()} tok</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Stats row */}
      <div style={S.statsRow} data-layout="stats">
        <StatCard label="Total Inputs" value={totalStr} />
        <StatCard label="Comparisons" value={compCount} />
        <StatCard label="Decided" value={decided} color="var(--green)" />
        <StatCard label="Pending" value={pending} color={pending > 0 ? 'var(--orange)' : 'var(--green)'} />
        <StatCard label="Decision Rate" value={compCount > 0 ? `${Math.round((decided / compCount) * 100)}%` : '—'} />
      </div>

      {/* Divergence dot plot — at-a-glance distribution */}
      {compCount > 0 && (
        <DivergenceDotPlot
          comparisons={comps}
          onDotClick={(c) => nav('compare', { compId: c.id })}
        />
      )}

      {/* Divergence histogram */}
      {compCount > 0 && (
        <div style={S.histPanel}>
          <div style={S.histH}>Divergence Distribution</div>
          <div style={S.histRow}>
            {buckets.map((n, i) => (
              <div key={i} style={S.histBar(n / maxBuck, BUCKET_COLORS[i])}>
                {n > 0 ? n : ''}
              </div>
            ))}
          </div>
          <div style={S.histLabels}>
            {BUCKET_LABELS.map(l => <div key={l} style={S.histLbl}>{l}</div>)}
          </div>
          {stats.choice_breakdown && (
            <div style={S.histLegend}>
              {Object.entries(stats.choice_breakdown).map(([k, v]) => (
                <span key={k} style={{ color: choiceColor(k) }}>
                  {k.toUpperCase()}: {v}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Cases table */}
      <div style={S.toolbar}>
        {['all','undecided','high'].map(f => (
          <button key={f} style={filterChip(filter === f)} onClick={() => setFilter(f)}>
            {f === 'all'
              ? `All (${comps.length})`
              : f === 'undecided'
                ? `Undecided (${pending})`
                : `High Δ (${comps.filter(c => (c.divergence_score || 0) >= 0.5).length})`
            }
          </button>
        ))}
        <input style={S.searchBox} value={search} onChange={e => setSearch(e.target.value)} placeholder="Search test cases…" />

        <div style={S.threshGroup}
             title="Only require verdicts on cases that diverge at least this much. Lower-divergence cases are unlikely to need review.">
          <span style={S.threshLabel}>Min Δ to review</span>
          <input type="range" min="0" max="100" step="5" value={Math.round(minDiv * 100)}
                 onChange={e => setMinDiv(parseInt(e.target.value) / 100)} style={{ width: 90 }}
                 aria-label="Minimum divergence to review" />
          <span style={S.threshVal}>{Math.round(minDiv * 100)}%</span>
        </div>

        {/* DPO Export — core differentiator, always visible */}
        <button style={S.dpoBtn} title="Export as DPO training data (prompt/chosen/rejected)" onClick={() => {
          const url = api.exportDpo(null, er.id)
          window.open(url, '_blank')
        }}>
          ⚡ Export DPO
        </button>

        {/* Export dropdown */}
        <div style={S.exportDropdown}>
          <button style={S.exportBtn} onClick={() => setShowExportMenu(v => !v)}>↓ Export ▾</button>
          {showExportMenu && (
            <div style={S.exportMenu} onMouseLeave={() => setShowExportMenu(false)}>
              <button style={S.exportMenuItem} onClick={() => { window.open(api.exportEvalRun(er.id), '_blank'); setShowExportMenu(false) }}>
                Decisions (JSONL)
              </button>
              <button style={S.exportMenuItem} onClick={() => { window.open(api.exportDecisions(null, er.id, 'csv'), '_blank'); setShowExportMenu(false) }}>
                Decisions (CSV)
              </button>
              <button style={S.exportMenuItem} onClick={() => { window.open(api.exportDpo(null, er.id), '_blank'); setShowExportMenu(false) }}>
                DPO Training Data (JSONL)
              </button>
              <button style={S.exportMenuItem} onClick={() => { window.open(api.exportOpenAiFt(null, er.id), '_blank'); setShowExportMenu(false) }}>
                OpenAI Fine-tuning (JSONL)
              </button>
              <button style={S.exportMenuItem} onClick={() => { window.open(api.exportPreferenceCorpus(er.id), '_blank'); setShowExportMenu(false) }}>
                Preference Corpus (JSONL)
              </button>
            </div>
          )}
        </div>

        {nextUndecided && (
          <button style={S.reviewNext} onClick={() => openComparison(nextUndecided.id)}>Review Next →</button>
        )}
      </div>

      {minDiv > 0 && (
        <div style={S.threshNote}>
          {aboveThresh} case{aboveThresh === 1 ? '' : 's'} at ≥{Math.round(minDiv * 100)}% divergence
          {needsReview.length > 0
            ? <> · <strong>{needsReview.length}</strong> still need a verdict.</>
            : <> · all reviewed ✓</>}
          {' '}Lower-divergence cases are hidden — they&rsquo;re unlikely to need your input, and DPO export already
          supports a matching <code>min_divergence</code> filter.
        </div>
      )}

      <div style={S.panel}>
        {filtered.length === 0
          ? <div style={S.empty}>No comparisons match filter</div>
          : (
            <table style={T.table}>
              <thead>
                <tr>
                  <th style={T.th}>#</th>
                  <th style={T.th}>Test Case</th>
                  <th style={T.th}>Divergence</th>
                  <th style={T.th}>Status</th>
                  <th style={T.th}>Decision</th>
                  <th style={T.th}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c, i) => (
                  <tr key={c.id} style={T.row}
                      onClick={() => openComparison(c.id)}
                      {...hoverHandlers}
                  >
                    <td style={{ ...T.td, color:'var(--muted)', fontSize:11 }}>{i+1}</td>
                    <td style={T.td}>
                      {c.test_case_label
                        ? <span style={{ fontWeight:500 }}>{c.test_case_label}</span>
                        : <span style={S.noData}>Case #{c.id.slice(-6)}</span>
                      }
                    </td>
                    <td style={T.td}>
                      {c.divergence_score != null
                        ? <span style={S.divChip(c.divergence_score)}>{(c.divergence_score * 100).toFixed(0)}%</span>
                        : <span style={S.noData}>—</span>
                      }
                    </td>
                    <td style={T.td}>
                      {c.decided
                        ? <span style={{ color:'var(--green)', fontSize:11, fontWeight:600 }}>✓ Decided</span>
                        : <span style={{ color:'var(--orange)', fontSize:11 }}>Pending</span>
                      }
                    </td>
                    <td style={T.td}>
                      {c.decided && c.choice
                        ? <span style={S.choiceChip(c.choice)}>
                            {c.choice === 'A' ? 'A wins' : c.choice === 'B' ? 'B wins' : c.choice}
                          </span>
                        : <span style={{ color:'var(--muted)', fontSize:11 }}>—</span>
                      }
                    </td>
                    <td style={{ ...T.td, color:'var(--accent)', fontSize:12, whiteSpace:'nowrap' }}>
                      {c.decided ? 'View →' : 'Review →'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </div>
    </div>
  )
}
