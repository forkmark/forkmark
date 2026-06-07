import { useState, useEffect } from 'react'
import { api } from '../api.js'
import {
  PageHeader, DivText, EmptyState, SkeletonTable,
  pageStyle, filterChip, divColor, fmtDateLong,
} from './ui'

const S = {
  expBtn:  { fontSize:12, padding:'6px 14px', background:'transparent', color:'var(--green)', border:'1px solid var(--green)', borderRadius:5, cursor:'pointer', fontWeight:600 },
  dpoBtn:  { fontSize:12, padding:'6px 14px', background:'linear-gradient(135deg,#7c3aed,#2563eb)', color:'#fff', border:'none', borderRadius:5, cursor:'pointer', fontWeight:700, marginRight:6 },
  exportWrap: { position:'relative', display:'inline-block' },
  exportMenu: { position:'absolute', right:0, top:'100%', marginTop:4, background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, boxShadow:'0 8px 24px rgba(0,0,0,.25)', zIndex:50, minWidth:200, padding:'4px 0' },
  exportItem: { display:'block', width:'100%', padding:'8px 14px', background:'none', border:'none', color:'var(--text)', fontSize:12, textAlign:'left', cursor:'pointer', fontWeight:500 },
  filters: { display:'flex', gap:8, marginBottom:16, flexWrap:'wrap' },
  cards:   { display:'flex', flexDirection:'column', gap:10 },
  card:    { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:'16px' },
  cardH:   { display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:10 },
  left2:   { display:'flex', alignItems:'center', gap:10 },
  choice:  (c) => {
    const m = { A:'var(--accent)', B:'var(--purple)', neither:'var(--muted)', both:'var(--green)' }
    return {
      fontWeight:700, fontSize:18, color: m[c]||'var(--text)',
      background: (m[c]||'var(--muted)')+'22', width:36, height:36,
      borderRadius:'50%', display:'flex', alignItems:'center', justifyContent:'center',
    }
  },
  choiceLabel:{ fontWeight:600, fontSize:13 },
  conf:    (c) => ({
    fontSize:11, padding:'2px 8px', borderRadius:10, fontWeight:600,
    color: c==='high' ? 'var(--green)' : c==='medium' ? 'var(--orange)' : 'var(--muted)',
    background: c==='high' ? 'rgba(74,222,128,0.12)' : c==='medium' ? 'rgba(251,191,36,0.12)' : 'rgba(107,115,148,0.12)',
  }),
  rat:     { fontSize:13, color:'var(--text)', lineHeight:1.6, marginBottom:8 },
  ratLabel:{ color:'var(--muted)', fontSize:11, marginRight:6 },
  tags:    { display:'flex', gap:6, flexWrap:'wrap', marginTop:8 },
  tag:     { fontSize:11, background:'var(--surface2)', padding:'2px 8px', borderRadius:10, color:'var(--muted)' },
  compLink:{ fontSize:11, color:'var(--accent)', cursor:'pointer', textDecoration:'underline' },
  date:    { fontSize:11, color:'var(--muted)' },
}

const CHOICES = ['all','A','B','neither','both']
const CONFS   = ['all','high','medium','low']

function choiceSymbol(c) {
  return { A:'A', B:'B', neither:'∅', both:'⊕' }[c] ?? c
}
function choiceLabel(c) {
  return { A:'Branch A', B:'Branch B', neither:'Neither', both:'Both' }[c] ?? c
}

export default function DecisionHistory({ workflowId, nav }) {
  const [decisions, setDecisions] = useState([])
  const [loading,   setLoading]   = useState(true)
  const [choiceF,   setChoiceF]   = useState('all')
  const [confF,     setConfF]     = useState('all')
  const [limit,     setLimit]     = useState(500)
  const [hasMore,   setHasMore]   = useState(false)
  const [showExport, setShowExport] = useState(false)

  useEffect(() => {
    if (!workflowId) return
    load(500)
  }, [workflowId])

  async function load(lim) {
    setLoading(true)
    const ds = await api.listDecisions(workflowId, null, lim + 1)
    const more = ds.length > lim
    setDecisions(more ? ds.slice(0, lim) : ds)
    setHasMore(more)
    setLimit(lim)
    setLoading(false)
  }

  function exportJSONL()  { window.open(api.exportDecisions(workflowId), '_blank') }
  function exportCSV()    { window.open(api.exportDecisions(workflowId, null, 'csv'), '_blank') }
  function exportDPO()    { window.open(api.exportDpo(workflowId), '_blank') }
  function exportOpenAI() { window.open(api.exportOpenAiFt(workflowId), '_blank') }

  const filtered = decisions.filter(d => {
    if (choiceF !== 'all' && d.choice !== choiceF) return false
    if (confF   !== 'all' && d.confidence !== confF) return false
    return true
  })

  const allTags = [...new Set(decisions.flatMap(d => d.tags || []))]

  return (
    <div style={pageStyle(1000)}>
      <PageHeader
        title="Decision History"
        subtitle={`${decisions.length} decisions recorded${allTags.length > 0 ? ` · ${allTags.length} unique tags` : ''}`}
        backLabel="← Workflow"
        onBack={() => nav('workflow', { workflowId })}
        right={
          <div style={S.exportWrap}>
            <button style={S.dpoBtn} onClick={exportDPO} title="Export DPO training pairs">⚡ Export DPO</button>
            <button style={S.expBtn} onClick={() => setShowExport(v => !v)}>↓ Export ▾</button>
            {showExport && (
              <div style={S.exportMenu} onMouseLeave={() => setShowExport(false)}>
                <button style={S.exportItem} onClick={() => { exportJSONL(); setShowExport(false) }}>📄 Decisions JSONL</button>
                <button style={S.exportItem} onClick={() => { exportCSV(); setShowExport(false) }}>📊 Decisions CSV</button>
                <button style={S.exportItem} onClick={() => { exportDPO(); setShowExport(false) }}>🧠 DPO Training Data</button>
                <button style={S.exportItem} onClick={() => { exportOpenAI(); setShowExport(false) }}>🤖 OpenAI Fine-tuning</button>
              </div>
            )}
          </div>
        }
      />

      <div style={S.filters}>
        <span style={{ fontSize:11, color:'var(--muted)', alignSelf:'center', marginRight:4 }}>Choice:</span>
        {CHOICES.map(c => (
          <button key={c} style={filterChip(choiceF===c)} onClick={() => setChoiceF(c)}>{c}</button>
        ))}
        <span style={{ fontSize:11, color:'var(--muted)', alignSelf:'center', marginLeft:8, marginRight:4 }}>Confidence:</span>
        {CONFS.map(c => (
          <button key={c} style={filterChip(confF===c)} onClick={() => setConfF(c)}>{c}</button>
        ))}
      </div>

      {loading && <SkeletonTable rows={5} />}
      {!loading && filtered.length === 0 && <EmptyState body="No decisions match filters" />}

      <div style={S.cards}>
        {filtered.map(d => (
          <div key={d.id} style={S.card}>
            <div style={S.cardH}>
              <div style={S.left2}>
                <div style={S.choice(d.choice)}>{choiceSymbol(d.choice)}</div>
                <div>
                  <div style={S.choiceLabel}>{choiceLabel(d.choice)}</div>
                  <span style={S.conf(d.confidence)}>{d.confidence} confidence</span>
                </div>
              </div>
              <div style={{ textAlign:'right' }}>
                <DivText score={d.divergence_score} />
                <div style={S.date}>{fmtDateLong(d.created_at)}</div>
                <div>
                  <span style={S.compLink} onClick={() => nav('compare', { compId: d.comparison_id })}>
                    Comp #{d.comparison_id} →
                  </span>
                </div>
              </div>
            </div>

            {d.rationale_for_choice && (
              <div style={S.rat}>
                <span style={S.ratLabel}>Why:</span>
                {d.rationale_for_choice}
              </div>
            )}
            {d.rationale_for_rejection && (
              <div style={{ ...S.rat, color:'var(--muted)' }}>
                <span style={S.ratLabel}>Rejected:</span>
                {d.rationale_for_rejection}
              </div>
            )}

            {d.tags?.length > 0 && (
              <div style={S.tags}>
                {d.tags.map(t => <span key={t} style={S.tag}>{t}</span>)}
              </div>
            )}
          </div>
        ))}
      </div>

      {hasMore && (
        <div style={{ textAlign:'center', marginTop:16 }}>
          <button
            style={{ fontSize:12, padding:'6px 18px', background:'transparent', color:'var(--accent)', border:'1px solid var(--accent)', borderRadius:5, cursor:'pointer' }}
            onClick={() => load(limit + 500)}
          >
            Load more ({decisions.length} shown)
          </button>
        </div>
      )}
    </div>
  )
}
