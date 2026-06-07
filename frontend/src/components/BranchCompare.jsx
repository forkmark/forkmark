import { useState, useEffect, useCallback } from 'react'
import { api, dispatchApiError, getReviewerId, setReviewerId } from '../api.js'
import CommentThread from './CommentThread.jsx'
import { divColor, divBg, modelCostPer1M } from './ui/constants.js'
import Breadcrumb from './ui/Breadcrumb.jsx'

function estimateCost(steps) {
  if (!steps?.length) return null
  let totalIn = 0, totalOut = 0
  let costUsd = 0
  let hasPrice = false
  for (const s of steps) {
    const src = s.branch_a || s
    totalIn  += src.tokens_input  || 0
    totalOut += src.tokens_output || 0
    const p = modelCostPer1M(src.model_id)
    if (p) {
      costUsd  += (src.tokens_input  || 0) / 1e6 * p[0]
      costUsd  += (src.tokens_output || 0) / 1e6 * p[1]
      hasPrice = true
    }
  }
  return { totalIn, totalOut, costUsd: hasPrice ? costUsd : null }
}

/* ── styles ────────────────────────────────────────────────────────── */
const S = {
  page:    { padding:'24px', maxWidth:1300 },
  head:    { display:'flex', alignItems:'center', gap:12, marginBottom:4 },
  back:    { background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:13, padding:0 },
  h1:      { fontSize:22, fontWeight:800, letterSpacing:'-0.03em' },
  meta:    { color:'var(--muted)', fontSize:13, marginBottom:20, display:'flex', alignItems:'center', gap:16 },
  divChip: (s) => ({
    fontWeight:700, fontSize:12,
    color: divColor(s), background: divBg(s),
    padding:'3px 10px', borderRadius:10,
  }),
  layout:  { display:'grid', gridTemplateColumns:'1fr 380px', gap:16, alignItems:'start' },
  steps:   { display:'flex', flexDirection:'column', gap:12 },
  stepBox: (highlight, divScore) => {
    const accent = divScore != null
      ? (divScore < 0.2 ? 'var(--green)' : divScore < 0.5 ? 'var(--orange)' : 'var(--red)')
      : 'var(--border)'
    return {
      background:'var(--surface)', border:'1px solid var(--border)',
      borderLeft: `3px solid ${accent}`,
      borderRadius:'2px 8px 8px 2px', overflow:'hidden',
    }
  },
  stepH:   {
    display:'flex', alignItems:'center', justifyContent:'space-between',
    padding:'10px 14px', background:'var(--surface2)', borderBottom:'1px solid var(--border)',
    fontSize:12,
  },
  stepName:{ fontWeight:600 },
  cols:    { display:'grid', gridTemplateColumns:'1fr 1fr', gap:0 },
  col:     (side) => ({
    padding:'14px',
    borderRight: side==='A' ? '1px solid var(--border)' : 'none',
  }),
  colHead: (side) => ({
    fontSize:10, fontWeight:600, color: side==='A' ? 'var(--accent)' : 'var(--purple)',
    textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:8,
    display:'flex', alignItems:'center', gap:6,
  }),
  output:  { fontSize:12, lineHeight:1.6, whiteSpace:'pre-wrap', wordBreak:'break-word' },
  diffWrap:{ fontSize:12, lineHeight:1.8, wordBreak:'break-word' },
  equal:   { color:'var(--text)' },
  added:   { background:'rgba(74,222,128,0.15)', color:'var(--green)', borderRadius:2, padding:'1px 2px' },
  removed: { background:'rgba(248,113,113,0.12)', color:'var(--red)', borderRadius:2, textDecoration:'line-through', padding:'1px 2px', opacity:0.75 },
  noStep:  { color:'var(--muted)', fontSize:12, fontStyle:'italic' },
  latency: { color:'var(--muted)', fontSize:11 },
  tokens:  { color:'var(--muted)', fontSize:11 },
  diffToggle:{ fontSize:11, background:'transparent', border:'1px solid var(--border)', color:'var(--muted)', padding:'2px 8px', borderRadius:4, cursor:'pointer' },

  // Decision panel
  decPanel:{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:0, position:'sticky', top:24 },
  decH:    { padding:'14px 16px', borderBottom:'1px solid var(--border)', fontWeight:600, fontSize:13 },
  decBody: { padding:'16px' },
  decSect: { marginBottom:16 },
  decLabel:{ fontSize:11, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:8, display:'block' },
  choiceRow:{ display:'flex', gap:8, marginBottom:12 },
  choiceBtn:(active,color) => ({
    flex:1, padding:'8px 0', border:`1px solid ${active ? color : 'var(--border)'}`,
    background: active ? color+'22' : 'transparent',
    color: active ? color : 'var(--muted)',
    borderRadius:6, cursor:'pointer', fontSize:12, fontWeight:600, transition:'all 0.15s',
  }),
  confRow: { display:'flex', gap:6, marginBottom:12 },
  confBtn: (active) => ({
    flex:1, padding:'6px 0', border:`1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
    background: active ? 'rgba(123,164,247,0.1)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--muted)',
    borderRadius:5, cursor:'pointer', fontSize:11, fontWeight:600,
  }),
  textarea:{ width:'100%', background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, color:'var(--text)', padding:'8px 10px', fontSize:12, resize:'vertical', boxSizing:'border-box', marginBottom:10, minHeight:70, fontFamily:'var(--font)' },
  tagInput:{ width:'100%', background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, color:'var(--text)', padding:'7px 10px', fontSize:12, boxSizing:'border-box', marginBottom:6, fontFamily:'var(--font)' },
  tagHint: { fontSize:11, color:'var(--muted)', marginBottom:12 },
  submitBtn:(disabled)=>({
    width:'100%', padding:'10px', background: disabled ? 'var(--border)' : 'var(--accent)',
    color: disabled ? 'var(--muted)' : 'var(--bg)', border:'none', borderRadius:6,
    fontWeight:700, fontSize:13, cursor: disabled ? 'not-allowed' : 'pointer', transition:'all 0.15s',
  }),
  decided: { textAlign:'center', padding:20 },
  dChoice: { fontSize:32, marginBottom:8 },
  dLabel:  { fontWeight:700, fontSize:15, marginBottom:4 },
  dSub:    { color:'var(--muted)', fontSize:12, marginBottom:12 },
  dRat:    { background:'var(--surface2)', borderRadius:6, padding:12, fontSize:12, textAlign:'left', color:'var(--text)', lineHeight:1.6 },
  editBtn: { marginTop:12, fontSize:11, background:'transparent', border:'1px solid var(--border)', color:'var(--muted)', padding:'4px 12px', borderRadius:4, cursor:'pointer' },

  // Input data panel
  inputPanel:{ background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, padding:'10px 14px', marginBottom:16 },
  inputH:    { fontSize:11, color:'var(--muted)', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:6 },
  inputData: { fontFamily:'var(--mono)', fontSize:11, color:'var(--text)', whiteSpace:'pre-wrap', wordBreak:'break-word', lineHeight:1.5 },

  // Tag autocomplete
  tagSuggestions:{ display:'flex', gap:4, flexWrap:'wrap', marginBottom:6 },
  tagSug:{ fontSize:10, padding:'2px 8px', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:10, cursor:'pointer', color:'var(--muted)' },

  // Keyboard shortcut hint
  kbHint:{ fontSize:10, color:'var(--muted)', textAlign:'right', marginBottom:6 },

  // Reviewer input
  reviewerRow:{ display:'flex', alignItems:'center', gap:6, marginBottom:14, paddingBottom:10, borderBottom:'1px solid var(--border)' },
  reviewerIcon:{ fontSize:13, color:'var(--muted)' },
  reviewerInput:{ flex:1, background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, color:'var(--text)', padding:'5px 8px', fontSize:11, fontFamily:'var(--font)' },

  // Cost comparison panel (inside decision panel)
  costRow:{ display:'flex', gap:8, marginBottom:12 },
  costCard:(side) => ({
    flex:1, background:'var(--surface2)', borderRadius:5, padding:'7px 10px',
    border:`1px solid ${side === 'A' ? 'rgba(123,164,247,0.2)' : 'rgba(196,161,245,0.2)'}`,
  }),
  costSide:{ fontSize:10, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.5px', marginBottom:3, color:'var(--muted)' },
  costVal: { fontSize:13, fontWeight:700, color:'var(--text)' },
  costTok: { fontSize:10, color:'var(--muted)', marginTop:2 },
  costDelta:{ fontSize:11, color:'var(--muted)', textAlign:'center', marginBottom:12 },
}

/* ── helpers ──────────────────────────────────────────────────────── */
function choiceLabel(c) {
  return { A:'Branch A', B:'Branch B', neither:'Neither', both:'Both' }[c] ?? c
}
function choiceColor(c) {
  return { A:'var(--accent)', B:'var(--purple)', neither:'var(--muted)', both:'var(--green)' }[c] ?? 'var(--text)'
}
function fmtMs(ms) {
  if (ms == null) return ''
  return ms >= 1000 ? `${(ms/1000).toFixed(1)}s` : `${ms}ms`
}

/* ── inline diff renderer ─────────────────────────────────────────── */
function DiffView({ tokens }) {
  if (!tokens?.length) return null
  return (
    <div style={S.diffWrap}>
      {tokens.map((t, i) => (
        <span key={i} style={S[t.type] || S.equal}>{t.text}{' '}</span>
      ))}
    </div>
  )
}

/* ── single step card ─────────────────────────────────────────────── */
function StepCard({ step, highlight }) {
  const [showDiff, setShowDiff] = useState(true)
  const { step_name, branch_a, branch_b, divergence_score, inline_diff } = step

  return (
    <div style={S.stepBox(highlight, divergence_score)}>
      <div style={S.stepH}>
        <span style={{ ...S.stepName, letterSpacing: '-0.01em' }}>{step_name || `Step ${step.step_index + 1}`}</span>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          {divergence_score != null && (
            <span style={S.divChip(divergence_score)}>
              Δ {(divergence_score * 100).toFixed(0)}%
            </span>
          )}
          {inline_diff && (
            <button style={S.diffToggle} onClick={() => setShowDiff(v => !v)}>
              {showDiff ? 'Raw' : 'Diff'}
            </button>
          )}
        </div>
      </div>

      <div style={S.cols}>
        {/* Branch A */}
        <div style={S.col('A')}>
          <div style={S.colHead('A')}>
            <span>A</span>
            <span style={{ color:'var(--muted)', fontWeight:400 }}>{branch_a?.model_id}</span>
            {branch_a && <span style={S.latency}>{fmtMs(branch_a.latency_ms)}</span>}
          </div>
          {branch_a
            ? <>
                <div style={S.output}>{branch_a.output_text || <em style={{ color:'var(--muted)' }}>(no output)</em>}</div>
                {(branch_a.tokens_input > 0 || branch_a.tokens_output > 0) && (
                  <div style={{ ...S.tokens, marginTop:6 }}>
                    {branch_a.tokens_input}↑ {branch_a.tokens_output}↓ tok
                  </div>
                )}
              </>
            : <div style={S.noStep}>No output for this step</div>
          }
        </div>

        {/* Branch B */}
        <div style={S.col('B')}>
          <div style={S.colHead('B')}>
            <span>B</span>
            <span style={{ color:'var(--muted)', fontWeight:400 }}>{branch_b?.model_id}</span>
            {branch_b && <span style={S.latency}>{fmtMs(branch_b.latency_ms)}</span>}
          </div>
          {branch_b
            ? <>
                {showDiff && inline_diff
                  ? <DiffView tokens={inline_diff} />
                  : <div style={S.output}>{branch_b.output_text || <em style={{ color:'var(--muted)' }}>(no output)</em>}</div>
                }
                {(branch_b.tokens_input > 0 || branch_b.tokens_output > 0) && (
                  <div style={{ ...S.tokens, marginTop:6 }}>
                    {branch_b.tokens_input}↑ {branch_b.tokens_output}↓ tok
                  </div>
                )}
              </>
            : <div style={S.noStep}>No output for this step</div>
          }
        </div>
      </div>
    </div>
  )
}

/* ── decision panel ───────────────────────────────────────────────── */
function DecisionPanel({ comp, onDecide, onBackToEval, existingTags }) {
  const [choice,     setChoice]     = useState('')
  const [conf,       setConf]       = useState('')
  const [ratFor,     setRatFor]     = useState('')
  const [ratAgainst, setRatAgainst] = useState('')
  const [tags,       setTags]       = useState('')
  const [reviewer,   setReviewer]   = useState(() => getReviewerId())
  const [loading,    setLoading]    = useState(false)
  const [editing,    setEditing]    = useState(false)

  const existing = comp?.decision
  const decided  = existing && !editing

  // Persist reviewer name for next comparison
  function handleReviewerChange(v) {
    setReviewer(v)
    setReviewerId(v)
  }

  // Cost estimate for branch A vs B
  const steps = comp?.steps || []
  const costA = estimateCost(steps.map(s => s.branch_a).filter(Boolean))
  const costB = estimateCost(steps.map(s => s.branch_b).filter(Boolean))

  // Keyboard shortcuts: A/1=A, B/2=B, N/3=neither, 4=both; H/M/L=confidence
  const handleKey = useCallback((e) => {
    if (decided) return
    if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return
    const k = e.key.toLowerCase()
    const choiceMap = { '1':'A', '2':'B', '3':'neither', '4':'both', 'a':'A', 'b':'B', 'n':'neither' }
    const confMap   = { 'h':'high', 'm':'medium', 'l':'low' }
    if (choiceMap[k]) { e.preventDefault(); setChoice(choiceMap[k]) }
    if (confMap[k])   { e.preventDefault(); setConf(confMap[k]) }
  }, [decided])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  // Tag autocomplete: existing tags not already in current input
  const currentTags = tags.split(',').map(t => t.trim()).filter(Boolean)
  const suggestions = (existingTags || []).filter(t => !currentTags.includes(t)).slice(0, 8)

  function addSuggestedTag(t) {
    const base = tags.trim()
    setTags(base ? base + ', ' + t : t)
  }

  async function submit() {
    if (!choice || !conf || ratFor.trim().length < 10) return
    setLoading(true)
    const payload = {
      reviewer_id:             reviewer.trim() || 'default',
      choice,
      confidence:              conf,
      rationale_for_choice:    ratFor.trim(),
      rationale_for_rejection: ratAgainst.trim(),
      tags: tags.split(',').map(t => t.trim()).filter(Boolean),
    }
    try {
      if (editing && existing) {
        await api.updateDecision(comp.id, payload)
      } else {
        await api.recordDecision(comp.id, payload)
      }
      setEditing(false)
      onDecide()
      window.dispatchEvent(new CustomEvent('fp:apisuccess', { detail: { message: 'Decision saved' } }))
    } catch (err) {
      dispatchApiError(err.message || 'Failed to save decision')
    } finally {
      setLoading(false)
    }
  }

  if (decided) {
    const d = existing
    return (
      <div style={S.decPanel}>
        <div style={S.decH}>Decision Recorded</div>
        <div style={{ ...S.decBody, ...S.decided }}>
          <div style={{ ...S.dChoice, color: choiceColor(d.choice) }}>
            {choiceLabel(d.choice)}
          </div>
          <div style={S.dLabel}>{d.confidence} confidence</div>
          {d.divergence_score != null && (
            <div style={S.dSub}>Divergence: {(d.divergence_score * 100).toFixed(0)}%</div>
          )}
          {d.rationale_for_choice && (
            <div style={S.dRat}><strong>Why:</strong> {d.rationale_for_choice}</div>
          )}
          {d.rationale_for_rejection && (
            <div style={{ ...S.dRat, marginTop:8 }}><strong>Rejected because:</strong> {d.rationale_for_rejection}</div>
          )}
          {d.tags?.length > 0 && (
            <div style={{ marginTop:8, display:'flex', flexWrap:'wrap', gap:4, justifyContent:'center' }}>
              {d.tags.map(t => (
                <span key={t} style={{ fontSize:11, background:'var(--surface2)', padding:'2px 8px', borderRadius:10, color:'var(--muted)' }}>{t}</span>
              ))}
            </div>
          )}
          {onBackToEval && (
            <button style={{ ...S.editBtn, color:'var(--accent)', borderColor:'var(--accent)', marginRight:4 }}
                    onClick={onBackToEval}>
              ← Back to Eval Run
            </button>
          )}
          <button style={S.editBtn} onClick={() => {
            setChoice(d.choice); setConf(d.confidence)
            setRatFor(d.rationale_for_choice||''); setRatAgainst(d.rationale_for_rejection||'')
            setTags((d.tags||[]).join(', ')); setEditing(true)
          }}>Edit Decision</button>
        </div>
      </div>
    )
  }

  const canSubmit = choice && conf && ratFor.trim().length >= 10 && !loading

  return (
    <div style={S.decPanel}>
      <div style={S.decH}>Record Decision</div>
      <div style={S.decBody}>
        {/* Reviewer identity — persisted across comparisons */}
        <div style={S.reviewerRow}>
          <span style={S.reviewerIcon}>👤</span>
          <input
            style={S.reviewerInput}
            value={reviewer}
            onChange={e => handleReviewerChange(e.target.value)}
            placeholder="Your name (optional)"
            aria-label="Reviewer name"
          />
        </div>

        <div style={S.kbHint}>A/1=A · B/2=B · N/3=∅ · 4=⊕ · H/M/L=confidence</div>

        <div style={S.decSect}>
          <span style={S.decLabel}>Which branch is better?</span>
          <div style={S.choiceRow}>
            {['A','B','neither','both'].map(c => (
              <button key={c} style={S.choiceBtn(choice===c, choiceColor(c))} onClick={() => setChoice(c)}
                      aria-label={choiceLabel(c)} aria-pressed={choice === c}>
                {c === 'A' ? 'A' : c === 'B' ? 'B' : c === 'neither' ? '∅' : '⊕'}
              </button>
            ))}
          </div>
          {choice && (
            <div style={{ fontSize:11, color: choiceColor(choice), textAlign:'center', marginTop:-6, marginBottom:8 }}>
              {choiceLabel(choice)}
            </div>
          )}
        </div>

        <div style={S.decSect}>
          <span style={S.decLabel}>Confidence</span>
          <div style={S.confRow}>
            {['high','medium','low'].map(c => (
              <button key={c} style={S.confBtn(conf===c)} onClick={() => setConf(c)}>
                {c}
              </button>
            ))}
          </div>
        </div>

        {/* Token cost comparison — only shown when at least one model has pricing data */}
        {(costA?.costUsd != null || costB?.costUsd != null) && (
          <div style={S.decSect}>
            <span style={S.decLabel}>Estimated Cost</span>
            <div style={S.costRow}>
              <div style={S.costCard('A')}>
                <div style={S.costSide}>Branch A</div>
                <div style={S.costVal}>
                  {costA?.costUsd != null ? `~$${costA.costUsd.toFixed(4)}` : '—'}
                </div>
                <div style={S.costTok}>
                  {(costA?.totalIn || 0) + (costA?.totalOut || 0)} tok
                </div>
              </div>
              <div style={S.costCard('B')}>
                <div style={S.costSide}>Branch B</div>
                <div style={S.costVal}>
                  {costB?.costUsd != null ? `~$${costB.costUsd.toFixed(4)}` : '—'}
                </div>
                <div style={S.costTok}>
                  {(costB?.totalIn || 0) + (costB?.totalOut || 0)} tok
                </div>
              </div>
            </div>
            {costA?.costUsd != null && costB?.costUsd != null && (
              <div style={S.costDelta}>
                {costA.costUsd < costB.costUsd
                  ? `A is ${(((costB.costUsd - costA.costUsd) / costB.costUsd) * 100).toFixed(0)}% cheaper`
                  : costB.costUsd < costA.costUsd
                    ? `B is ${(((costA.costUsd - costB.costUsd) / costA.costUsd) * 100).toFixed(0)}% cheaper`
                    : 'Same estimated cost'
                }
              </div>
            )}
          </div>
        )}

        <div style={S.decSect}>
          <span style={S.decLabel}>Why did you choose this? *</span>
          <textarea style={S.textarea}
            value={ratFor}
            onChange={e => setRatFor(e.target.value)}
            placeholder="Explain why this branch is better (min 10 chars)..."
            aria-label="Rationale for choice"
          />
        </div>

        <div style={S.decSect}>
          <span style={S.decLabel}>What's wrong with the other?</span>
          <textarea style={{ ...S.textarea, minHeight:50 }}
            value={ratAgainst}
            onChange={e => setRatAgainst(e.target.value)}
            placeholder="Optional — why was the other branch rejected?"
            aria-label="Rationale for rejection"
          />
        </div>

        <div style={S.decSect}>
          <span style={S.decLabel}>Tags</span>
          {suggestions.length > 0 && (
            <div style={S.tagSuggestions}>
              {suggestions.map(t => (
                <button key={t} style={S.tagSug} onClick={() => addSuggestedTag(t)}>{t}</button>
              ))}
            </div>
          )}
          <input style={S.tagInput} value={tags} onChange={e=>setTags(e.target.value)}
            placeholder="tone, accuracy, hallucination, ..." aria-label="Decision tags" />
          <div style={S.tagHint}>Comma-separated · builds your taxonomy</div>
        </div>

        <button style={S.submitBtn(!canSubmit)} disabled={!canSubmit} onClick={submit}>
          {loading ? 'Saving...' : 'Submit Decision'}
        </button>
      </div>
    </div>
  )
}

/* ── main component ───────────────────────────────────────────────── */
export default function BranchCompare({ compId, nav, evalRunId }) {
  const [comp,        setComp]       = useState(null)
  const [loading,     setLoading]    = useState(true)
  const [allTags,     setAllTags]    = useState([])
  const [showInput,   setShowInput]  = useState(false)

  async function load() {
    if (!compId) return
    setLoading(true)
    try {
      const c = await api.getComparison(compId)
      setComp(c)
    } catch (err) {
      dispatchApiError(err.message || 'Failed to load comparison')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [compId])

  // Load existing tag taxonomy once for autocomplete
  useEffect(() => {
    api.listTags().then(data => setAllTags(data?.tags || [])).catch(() => {})
  }, [])

  if (!compId) return <div style={{ padding:24, color:'var(--muted)' }}>No comparison selected</div>
  if (loading) return (
    <div style={{ padding:24 }}>
      <div style={{ height:20, width:200, background:'var(--surface)', borderRadius:4, marginBottom:12 }} />
      <div style={{ height:14, width:300, background:'var(--surface)', borderRadius:4, marginBottom:20 }} />
      <div style={{ display:'grid', gridTemplateColumns:'1fr 380px', gap:16 }} data-layout="compare">
        <div>
          {[1,2].map(i => (
            <div key={i} style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, height:180, marginBottom:12 }} />
          ))}
        </div>
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, height:400 }} />
      </div>
    </div>
  )
  if (!comp)    return <div style={{ padding:24, color:'var(--red)' }}>Comparison not found</div>

  const steps      = comp.steps || []
  const overallDiv = comp.divergence_score
  const erId       = evalRunId || comp.eval_run?.id

  // Find the highest-diverging step to highlight it
  const stepDivScores = comp.step_divergence_scores || {}
  const maxDivStep = Object.keys(stepDivScores).length > 1
    ? Object.entries(stepDivScores).sort((a,b) => b[1] - a[1])[0]?.[0]
    : null

  return (
    <div style={S.page}>
      <Breadcrumb items={[
        ...(erId ? [
          { label: 'Results', onClick: () => nav('evalRuns') },
          { label: comp.eval_run?.name || 'Eval Run', onClick: () => nav('evalRunDetail', { evalRunId: erId }) },
        ] : [
          { label: 'Dashboard', onClick: () => nav('dashboard') },
        ]),
        { label: comp.test_case_label || `Compare #${comp.id}` },
      ]} />
      <div style={S.head}>
        <div style={{ ...S.h1, letterSpacing: '-0.03em', fontWeight: 800 }}>
          {comp.test_case_label ? comp.test_case_label : `Compare #${comp.id}`}
        </div>
        {comp.test_case_label && <span style={{ fontSize:12, color:'var(--muted)' }}>#{comp.id}</span>}
      </div>
      <div style={S.meta}>
        {erId && <span style={{ color:'var(--accent)', fontSize:12 }}>{comp.eval_run?.name}</span>}
        <span>Run #{comp.run_id}</span>
        {overallDiv != null && (
          <span style={S.divChip(overallDiv)}>
            Overall divergence {(overallDiv * 100).toFixed(0)}%
          </span>
        )}
        {comp.divergence_summary && (
          <span>{comp.divergence_summary}</span>
        )}
        {comp.decided && <span style={{ color:'var(--green)' }}>✓ Decided</span>}
      </div>

      {/* Input data toggle */}
      {comp.run_input && Object.keys(comp.run_input).length > 0 && (
        <div style={S.inputPanel}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', cursor:'pointer' }}
               onClick={() => setShowInput(v => !v)}>
            <div style={S.inputH}>Input Data</div>
            <span style={{ fontSize:11, color:'var(--muted)' }}>{showInput ? '▾' : '▸'}</span>
          </div>
          {showInput && (
            <div style={S.inputData}>{JSON.stringify(comp.run_input, null, 2)}</div>
          )}
        </div>
      )}

      <div style={S.layout} data-layout="compare">
        <div style={S.steps}>
          {steps.length === 0
            ? <div style={{ color:'var(--muted)', fontSize:13 }}>No steps logged for this comparison.</div>
            : steps.map((step, i) => (
              <StepCard key={i} step={step}
                highlight={maxDivStep != null && step.step_name === maxDivStep} />
            ))
          }
        </div>

        <div>
          <DecisionPanel comp={comp} onDecide={load} existingTags={allTags}
            onBackToEval={erId ? () => nav('evalRunDetail', { evalRunId: erId }) : null} />
          <CommentThread comparisonId={compId} />
        </div>
      </div>
    </div>
  )
}
