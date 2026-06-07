import { useState, useEffect, useCallback } from 'react'
import { api, dispatchApiError } from '../api.js'
import PageHeader from './ui/PageHeader.jsx'
import { pageStyle, panel, btnPrimary, btnSecondary, btnDanger } from './ui/styles.js'

// ── Styles ────────────────────────────────────────────────────────────────

const S = {
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
    gap: 16,
    marginBottom: 24,
  },
  card: (isAgent) => ({
    ...panel,
    padding: 0,
    overflow: 'hidden',
    transition: 'border-color 0.15s, box-shadow 0.15s',
    cursor: 'default',
    borderLeft: isAgent ? '3px solid var(--purple, #a78bfa)' : '3px solid var(--accent)',
    borderRadius: '2px 8px 8px 2px',
  }),
  cardHeader: {
    padding: '16px 18px 12px',
    borderBottom: '1px solid var(--border)',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  cardTitle: {
    fontSize: 15, fontWeight: 700, marginBottom: 4, letterSpacing: '-0.02em',
  },
  cardDesc: {
    fontSize: 12, color: 'var(--muted)', lineHeight: 1.5,
  },
  badge: (color) => ({
    fontSize: 10, fontWeight: 700, padding: '2px 8px',
    borderRadius: 10, whiteSpace: 'nowrap', flexShrink: 0,
    background: color === 'accent' ? 'rgba(123,164,247,0.15)'
              : color === 'agent'  ? 'rgba(167,139,250,0.15)'
              :                      'rgba(74,222,128,0.15)',
    color: color === 'accent' ? 'var(--accent)'
         : color === 'agent'  ? 'var(--purple, #a78bfa)'
         :                      'var(--green)',
    border: `1px solid ${
      color === 'accent' ? 'rgba(123,164,247,0.3)'
    : color === 'agent'  ? 'rgba(167,139,250,0.3)'
    :                      'rgba(74,222,128,0.3)'}`,
  }),
  cardBody: {
    padding: '12px 18px 16px',
  },
  meta: {
    display: 'flex', flexWrap: 'wrap', gap: 12,
    fontSize: 12, color: 'var(--muted)', marginBottom: 12,
  },
  metaItem: {
    display: 'flex', alignItems: 'center', gap: 5,
  },
  metaLabel: { opacity: 0.7 },
  metaVal: { fontWeight: 600, color: 'var(--text)' },
  branches: {
    display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12,
  },
  branchTag: (isA) => ({
    fontSize: 11, padding: '3px 10px', borderRadius: 4,
    background: isA ? 'rgba(123,164,247,0.1)' : 'rgba(251,191,36,0.1)',
    color: isA ? 'var(--accent)' : 'var(--orange)',
    border: `1px solid ${isA ? 'rgba(123,164,247,0.2)' : 'rgba(251,191,36,0.2)'}`,
  }),
  steps: {
    display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8,
  },
  stepTag: {
    fontSize: 10, padding: '2px 8px', borderRadius: 3,
    background: 'rgba(107,115,148,0.1)',
    color: 'var(--muted)',
    border: '1px solid var(--border)',
    fontFamily: 'monospace',
  },
  actions: {
    padding: '12px 18px', borderTop: '1px solid var(--border)',
    display: 'flex', gap: 8, justifyContent: 'flex-end',
  },
  seedAll: {
    ...btnPrimary,
    fontSize: 14,
    padding: '10px 24px',
  },
  progress: {
    height: 3, borderRadius: 2, overflow: 'hidden',
    background: 'rgba(123,164,247,0.15)',
    marginTop: 8,
  },
  progressBar: (pct) => ({
    height: '100%', width: `${pct}%`,
    background: 'var(--accent)',
    transition: 'width 0.3s ease',
  }),
  empty: {
    textAlign: 'center', padding: '60px 40px',
    color: 'var(--muted)', fontSize: 14,
  },
  statusRow: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '12px 18px', borderTop: '1px solid var(--border)',
    fontSize: 12,
  },
  spinner: {
    display: 'inline-block', width: 14, height: 14,
    border: '2px solid var(--border)',
    borderTopColor: 'var(--accent)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
}

// Inject keyframe animation
if (typeof document !== 'undefined' && !document.getElementById('fp-spin-keyframes')) {
  const style = document.createElement('style')
  style.id = 'fp-spin-keyframes'
  style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
  document.head.appendChild(style)
}

// ── Demo Card ──────────────────────────────────────────────────────────────

function DemoCard({ demo, seeding, seeded, onSeed, onView, onReset }) {
  const isLifecycle = demo.name === 'quickstart'
  const isAgent = demo.demo_type === 'agent'
  return (
    <div style={S.card(isAgent)}>
      <div style={S.cardHeader}>
        <div>
          <div style={S.cardTitle}>{demo.display_name}</div>
          <div style={S.cardDesc}>{demo.description}</div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {isAgent && <span style={S.badge('agent')}>AGENT</span>}
          {isLifecycle && <span style={S.badge('accent')}>FULL TOUR</span>}
        </div>
      </div>

      <div style={S.cardBody}>
        <div style={S.meta}>
          <div style={S.metaItem}>
            <span style={S.metaLabel}>Cases:</span>
            <span style={S.metaVal}>{demo.cases}</span>
          </div>
          {isAgent ? (
            <div style={S.metaItem}>
              <span style={S.metaLabel}>Trace Events:</span>
              <span style={S.metaVal}>{demo.trace_events || 0}</span>
            </div>
          ) : (
            <div style={S.metaItem}>
              <span style={S.metaLabel}>Steps:</span>
              <span style={S.metaVal}>{demo.steps}</span>
            </div>
          )}
        </div>

        <div style={S.branches}>
          <span style={S.branchTag(true)}>{demo.branch_a_label || 'Branch A'}</span>
          <span style={{ fontSize: 11, color: 'var(--muted)', alignSelf: 'center' }}>vs</span>
          <span style={S.branchTag(false)}>{demo.branch_b_label || 'Branch B'}</span>
        </div>

        {!isAgent && (
          <div style={S.steps}>
            {(demo.step_names || []).map(s => (
              <span key={s} style={S.stepTag}>{s.replace(/_/g, ' ')}</span>
            ))}
          </div>
        )}
      </div>

      {seeding && (
        <div style={S.statusRow}>
          <span style={S.spinner} />
          <span style={{ color: isAgent ? 'var(--purple, #a78bfa)' : 'var(--accent)' }}>Seeding demo data...</span>
        </div>
      )}

      <div style={S.actions}>
        {seeded ? (
          <>
            <button
              style={{ ...btnSecondary, fontSize: 12 }}
              onClick={() => onReset(demo.name)}
              disabled={seeding}
            >
              Reset
            </button>
            <button
              style={{ ...btnPrimary, fontSize: 12, padding: '6px 14px' }}
              onClick={() => onView(demo)}
            >
              {isAgent ? 'View Agent Runs →' : 'View Eval Run →'}
            </button>
          </>
        ) : (
          <button
            style={{ ...btnPrimary, fontSize: 12, padding: '6px 14px' }}
            onClick={() => onSeed(demo.name)}
            disabled={seeding}
          >
            {seeding ? 'Seeding...' : 'Seed Demo'}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function DemoGallery({ nav }) {
  const [demos, setDemos]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [seeding, setSeeding]     = useState({})    // { demoName: true }
  const [seeded, setSeeded]       = useState({})     // { demoName: resultObj }
  const [seedingAll, setSeedingAll] = useState(false)
  const [seedAllProgress, setSeedAllProgress] = useState(0)

  const fetchDemos = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.listDemos()
      // Sort: quickstart first, then LLM demos alphabetically, then agent demos alphabetically
      data.sort((a, b) => {
        if (a.name === 'quickstart') return -1
        if (b.name === 'quickstart') return 1
        // LLM demos before agent demos
        if (a.demo_type !== b.demo_type) {
          return a.demo_type === 'agent' ? 1 : -1
        }
        return a.display_name.localeCompare(b.display_name)
      })
      setDemos(data)
    } catch (e) {
      dispatchApiError('Failed to load demo gallery: ' + e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Check which demos are already seeded
  const checkSeeded = useCallback(async () => {
    try {
      const [workflows, evalRuns] = await Promise.all([
        api.listWorkflows(),
        api.listEvalRuns(),
      ])
      const wfByName = {}
      for (const wf of workflows) wfByName[wf.name] = wf

      const seededMap = {}
      for (const d of demos) {
        const wf = wfByName[d.workflow_name]
        if (wf) {
          const ers = evalRuns.filter(er => er.workflow_id === wf.id)
          if (ers.length > 0) {
            seededMap[d.name] = { workflow_id: wf.id, eval_run_id: ers[0].id }
          }
        }
      }
      setSeeded(seededMap)
    } catch {
      // Not critical — seeded status will just be unknown
    }
  }, [demos])

  useEffect(() => { fetchDemos() }, [fetchDemos])
  useEffect(() => { if (demos.length) checkSeeded() }, [demos, checkSeeded])

  async function seedOne(name) {
    setSeeding(s => ({ ...s, [name]: true }))
    try {
      const result = await api.seedDemos({ demos: [name] })
      const r = result.results?.[0]
      if (r && !r.error) {
        setSeeded(s => ({ ...s, [name]: { workflow_id: r.workflow_id, eval_run_id: r.eval_run_id } }))
        window.dispatchEvent(new CustomEvent('fp:apisuccess', {
          detail: { message: `${name} demo seeded: ${r.cases} cases, ${r.comparisons} comparisons` }
        }))
      } else {
        dispatchApiError(`Failed to seed ${name}: ${r?.error || 'Unknown error'}`)
      }
    } catch (e) {
      dispatchApiError(`Failed to seed ${name}: ${e.message}`)
    } finally {
      setSeeding(s => ({ ...s, [name]: false }))
    }
  }

  async function seedAll() {
    setSeedingAll(true)
    setSeedAllProgress(0)
    const total = demos.length
    let done = 0
    for (const d of demos) {
      if (seeded[d.name]) { done++; continue }
      setSeeding(s => ({ ...s, [d.name]: true }))
      try {
        const result = await api.seedDemos({ demos: [d.name] })
        const r = result.results?.[0]
        if (r && !r.error) {
          setSeeded(s => ({ ...s, [d.name]: { workflow_id: r.workflow_id, eval_run_id: r.eval_run_id } }))
        }
      } catch { /* continue seeding others */ }
      setSeeding(s => ({ ...s, [d.name]: false }))
      done++
      setSeedAllProgress(Math.round((done / total) * 100))
    }
    setSeedingAll(false)
    window.dispatchEvent(new CustomEvent('fp:apisuccess', {
      detail: { message: `All demos seeded successfully` }
    }))
  }

  async function resetOne(name) {
    try {
      await api.resetDemos({ demos: [name] })
      setSeeded(s => {
        const next = { ...s }
        delete next[name]
        return next
      })
      window.dispatchEvent(new CustomEvent('fp:apisuccess', {
        detail: { message: `${name} demo data reset` }
      }))
    } catch (e) {
      dispatchApiError(`Failed to reset ${name}: ${e.message}`)
    }
  }

  function viewDemo(demo) {
    const info = seeded[demo.name]
    if (demo.demo_type === 'agent') {
      // Agent demos route to the Agent Runs view
      nav('agentCompare', info?.eval_run_id ? { evalRunId: info.eval_run_id } : {})
    } else if (info?.eval_run_id) {
      nav('evalRunDetail', { evalRunId: info.eval_run_id })
    } else if (info?.workflow_id) {
      nav('workflow', { workflowId: info.workflow_id })
    }
  }

  const seededCount = Object.keys(seeded).length
  const allSeeded = seededCount === demos.length

  return (
    <div style={pageStyle(1200)}>
      <PageHeader
        title="Demo Gallery"
        subtitle={`${demos.length} industry demos ready to explore. Seed demo data to see Forkmark in action.`}
        right={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {seededCount > 0 && (
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                {seededCount}/{demos.length} seeded
              </span>
            )}
          </div>
        }
        action={allSeeded ? null : {
          label: seedingAll ? 'Seeding...' : 'Seed All Demos',
          onClick: seedAll,
        }}
      />

      {seedingAll && (
        <div style={S.progress}>
          <div style={S.progressBar(seedAllProgress)} />
        </div>
      )}

      {loading ? (
        <div style={S.empty}>Loading demos...</div>
      ) : demos.length === 0 ? (
        <div style={S.empty}>
          <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.3 }}>&#x1F4E6;</div>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>No demos found</div>
          <div>Place fixture files in <code>examples/*/fixtures.json</code> (LLM) or <code>examples/*/agent_fixtures.json</code> (Agent) to add demos.</div>
        </div>
      ) : (
        <>
          {/* LLM Comparison Demos */}
          {demos.some(d => d.demo_type !== 'agent') && (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
                LLM Comparison Demos
              </div>
              <div style={S.grid}>
                {demos.filter(d => d.demo_type !== 'agent').map(d => (
                  <DemoCard
                    key={d.name}
                    demo={d}
                    seeding={seeding[d.name]}
                    seeded={seeded[d.name]}
                    onSeed={seedOne}
                    onView={viewDemo}
                    onReset={resetOne}
                  />
                ))}
              </div>
            </>
          )}

          {/* Agent Comparison Demos */}
          {demos.some(d => d.demo_type === 'agent') && (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--purple, #a78bfa)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10, marginTop: 24 }}>
                Agent Trajectory Demos
              </div>
              <div style={S.grid}>
                {demos.filter(d => d.demo_type === 'agent').map(d => (
                  <DemoCard
                    key={d.name}
                    demo={d}
                    seeding={seeding[d.name]}
                    seeded={seeded[d.name]}
                    onSeed={seedOne}
                    onView={viewDemo}
                    onReset={resetOne}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
