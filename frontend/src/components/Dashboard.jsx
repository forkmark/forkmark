import { useState, useEffect } from 'react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api, dispatchApiError } from '../api.js'
import {
  StatCard, DivBadge, EmptyState, PageHeader, Modal, ModalFooter,
  pageStyle, panel, panelHeader, tableStyles as T, btnPrimary, formStyles as F,
  statusBadge, hoverHandlers,
} from './ui'

// ── Welcome Screen (empty-state / first-run) ─────────────────────────────────

const W = {
  wrap: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', minHeight: 'calc(100vh - 80px)',
    padding: '40px 24px', textAlign: 'center',
  },
  logo: {
    width: 72, height: 72, borderRadius: 16,
    background: 'linear-gradient(135deg, rgba(123,164,247,0.15), rgba(196,161,245,0.15))',
    border: '1px solid rgba(123,164,247,0.2)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 36, marginBottom: 24,
  },
  title: {
    fontSize: 30, fontWeight: 800, color: 'var(--text)', marginBottom: 8,
    letterSpacing: '-0.04em',
  },
  subtitle: {
    fontSize: 15, color: 'var(--muted)', maxWidth: 520, lineHeight: 1.6,
    marginBottom: 32,
  },
  actions: {
    display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center',
    marginBottom: 48,
  },
  primaryBtn: {
    padding: '12px 28px', fontSize: 15, fontWeight: 600,
    background: 'var(--accent)', color: 'var(--bg)', border: 'none',
    borderRadius: 8, cursor: 'pointer',
    transition: 'background 0.15s, transform 0.1s',
  },
  secondaryBtn: {
    padding: '12px 28px', fontSize: 15, fontWeight: 600,
    background: 'transparent', color: 'var(--accent)',
    border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  featureGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: 16, maxWidth: 700, width: '100%',
  },
  featureCard: {
    padding: '20px 16px', borderRadius: 10,
    background: 'var(--surface)', border: '1px solid var(--border)',
    textAlign: 'left',
  },
  featureIcon: {
    fontSize: 22, marginBottom: 8,
  },
  featureTitle: {
    fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 4, letterSpacing: '-0.01em',
  },
  featureDesc: {
    fontSize: 12, color: 'var(--muted)', lineHeight: 1.5,
  },
}

function WelcomeScreen({ nav }) {
  const features = [
    { icon: '↔️', title: 'Compare Branches', desc: 'Run the same prompt through two models and see outputs side-by-side with inline diffs.' },
    { icon: '✅', title: 'Human Review', desc: 'Record preference decisions with rationale, confidence, and tags for every comparison.' },
    { icon: '📦', title: 'DPO Export', desc: 'Export decisions as DPO/RLHF training data in one click — ready for fine-tuning.' },
  ]

  return (
    <div style={W.wrap}>
      <div style={W.logo}>
        <span role="img" aria-label="fork">&#x1F500;</span>
      </div>
      <div style={W.title}>Welcome to Forkmark</div>
      <div style={W.subtitle}>
        Compare LLM outputs side-by-side, collect human preference decisions,
        and export training data — all self-hosted, zero cloud dependency.
      </div>
      <div style={W.actions}>
        <button style={W.primaryBtn} onClick={() => nav('demos')}>
          Load Demo Data
        </button>
        <button style={W.secondaryBtn} onClick={() => nav('quickstart')}>
          Quick Start Guide
        </button>
        <button style={W.secondaryBtn} onClick={() => nav('playground')}>
          Open Playground
        </button>
      </div>
      <div style={W.featureGrid}>
        {features.map(f => (
          <div key={f.title} style={W.featureCard}>
            <div style={W.featureIcon}>{f.icon}</div>
            <div style={W.featureTitle}>{f.title}</div>
            <div style={W.featureDesc}>{f.desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function Dashboard({ nav }) {
  const [stats,     setStats]     = useState(null)
  const [workflows, setWorkflows] = useState([])
  const [pending,   setPending]   = useState([])
  const [evalRuns,  setEvalRuns]  = useState([])
  const [showNew,   setShowNew]   = useState(false)
  const [loading,   setLoading]   = useState(true)
  const [charts,    setCharts]    = useState(null)

  async function load() {
    try {
      const [s, wfs, comps, ers, ch] = await Promise.all([
        api.stats(),
        api.listWorkflows(),
        api.listComparisons(null, true),
        api.listEvalRuns(),
        api.statsCharts().catch(() => null),
      ])
      setStats(s)
      setWorkflows(wfs || [])
      setPending(comps || [])
      setEvalRuns((ers || []).slice(0, 5))
      setCharts(ch)
    } catch (e) {
      dispatchApiError(e.message || 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // First-run detection: no workflows AND no eval runs = show welcome
  const isEmpty = !loading && workflows.length === 0 && evalRuns.length === 0

  if (loading) {
    return (
      <div style={{ padding: 40, color: 'var(--muted)', fontSize: 13 }}>Loading...</div>
    )
  }

  if (isEmpty) {
    return <WelcomeScreen nav={nav} />
  }

  return (
    <div style={pageStyle(1100)}>
      <PageHeader title="Dashboard" subtitle="Overview of your AI workflow QA pipeline" />

      {/* Stat cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:28 }} data-layout="stats">
        <StatCard label="Eval Runs"      value={stats?.total_eval_runs}  color="var(--accent)" />
        <StatCard label="Decisions Made" value={stats?.total_decisions}  color="var(--green)" />
        <StatCard label="Pending Review" value={stats?.pending_review}   color={stats?.pending_review > 0 ? 'var(--orange)' : undefined} />
        <StatCard label="Workflows"      value={stats?.total_workflows} />
      </div>

      {/* Charts row: divergence histogram + cost over time */}
      {charts && (charts.divergence_histogram?.some(d => d.count > 0) || charts.cost_over_time?.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }} data-layout="playground">
          {/* Divergence Histogram */}
          {charts.divergence_histogram?.some(d => d.count > 0) && (
            <div style={panel}>
              <div style={panelHeader}><span>Divergence Distribution</span></div>
              <div style={{ padding: '12px 8px 8px', height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={charts.divergence_histogram} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="range" tick={{ fontSize: 10, fill: 'var(--muted)' }} interval={0} angle={-30} textAnchor="end" height={40} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, color: 'var(--text)' }}
                      cursor={{ fill: 'rgba(123,164,247,0.08)' }}
                    />
                    <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Cost Over Time */}
          {charts.cost_over_time?.length > 0 && (
            <div style={panel}>
              <div style={panelHeader}><span>Estimated Cost Over Time</span></div>
              <div style={{ padding: '12px 8px 8px', height: 220 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={charts.cost_over_time} margin={{ top: 4, right: 8, bottom: 0, left: -4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--muted)' }} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--muted)' }} tickFormatter={v => `$${v}`} />
                    <Tooltip
                      contentStyle={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, color: 'var(--text)' }}
                      formatter={(v, name) => [name === 'cost' ? `$${v.toFixed(4)}` : v.toLocaleString(), name === 'cost' ? 'Est. Cost' : 'Tokens']}
                    />
                    <Line type="monotone" dataKey="cost" stroke="var(--green)" strokeWidth={2} dot={{ r: 3, fill: 'var(--green)' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recent Eval Runs */}
      {evalRuns.length > 0 && (
        <div style={{ ...panel, marginBottom:16 }}>
          <div style={panelHeader}>
            <span>Recent Eval Runs</span>
            <button style={{ fontSize:12, background:'none', border:'none', color:'var(--accent)', cursor:'pointer' }}
                    onClick={() => nav('evalRuns')}>View all &rarr;</button>
          </div>
          <table style={T.table}>
            <thead>
              <tr>
                <th style={T.th}>Name</th>
                <th style={T.th}>Status</th>
                <th style={T.th}>Comparisons</th>
                <th style={T.th}>Decided</th>
                <th style={T.th}>Avg &Delta;</th>
              </tr>
            </thead>
            <tbody>
              {evalRuns.map(er => {
                const s = er.stats || {}
                return (
                  <tr key={er.id} style={T.row}
                      onClick={() => nav('evalRunDetail', { evalRunId: er.id })}
                      {...hoverHandlers}
                  >
                    <td style={T.td}><span style={{ fontWeight:500 }}>{er.name}</span></td>
                    <td style={T.td}><span style={statusBadge(er.status)}>{er.status}</span></td>
                    <td style={T.td}>{s.total || 0}</td>
                    <td style={T.td}>{s.decided || 0}</td>
                    <td style={T.td}><DivBadge score={s.avg_divergence} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        {/* Workflows */}
        <div style={panel}>
          <div style={panelHeader}>
            <span>Workflows</span>
            <button style={btnPrimary} onClick={() => setShowNew(true)}>+ New</button>
          </div>
          {workflows.length === 0
            ? <EmptyState body="No workflows yet" />
            : (
              <table style={T.table}>
                <thead>
                  <tr>
                    <th style={T.th}>Name</th>
                    <th style={T.th}>Runs</th>
                    <th style={T.th}>Decisions</th>
                  </tr>
                </thead>
                <tbody>
                  {workflows.map(wf => (
                    <tr key={wf.id} style={T.row}
                        onClick={() => nav('workflow', { workflowId: wf.id })}
                        {...hoverHandlers}
                    >
                      <td style={T.td}>
                        <div style={{ fontWeight:500 }}>{wf.name}</div>
                        {wf.description && <div style={{ color:'var(--muted)', fontSize:11, marginTop:2 }}>{wf.description}</div>}
                      </td>
                      <td style={T.td}>{wf.run_count ?? 0}</td>
                      <td style={T.td}>{wf.decision_count ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>

        {/* Pending Reviews */}
        <div style={panel}>
          <div style={panelHeader}>
            <span>Pending Review</span>
            <span style={{
              background: pending.length > 0 ? 'rgba(248,113,113,0.15)' : 'rgba(74,222,128,0.15)',
              color: pending.length > 0 ? 'var(--red)' : 'var(--green)',
              fontSize:11, padding:'2px 8px', borderRadius:10, fontWeight:600,
            }}>{pending.length}</span>
          </div>
          {pending.length === 0
            ? <div style={{ padding:24, color:'var(--muted)', textAlign:'center', fontSize:13 }}>All caught up &#x2713;</div>
            : (
              <table style={T.table}>
                <thead>
                  <tr>
                    <th style={T.th}>Run</th>
                    <th style={T.th}>Divergence</th>
                    <th style={T.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map(c => (
                    <tr key={c.id} style={T.row}
                        onClick={() => nav('compare', { compId: c.id })}
                        {...hoverHandlers}
                    >
                      <td style={T.td}>
                        <div style={{ fontWeight:500, fontSize:12 }}>Run #{c.run_id}</div>
                        <div style={{ color:'var(--muted)', fontSize:11 }}>Comp #{c.id}</div>
                      </td>
                      <td style={T.td}><DivBadge score={c.divergence_score} /></td>
                      <td style={{ ...T.td, color:'var(--accent)', fontSize:12 }}>Review &rarr;</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      </div>

      {showNew && (
        <NewWorkflowModal
          onClose={() => setShowNew(false)}
          onCreate={() => load()}
        />
      )}
    </div>
  )
}

function NewWorkflowModal({ onClose, onCreate }) {
  const [name, setName]       = useState('')
  const [desc, setDesc]       = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    try {
      await api.createWorkflow({ name: name.trim(), description: desc.trim() })
      onCreate()
      onClose()
    } catch (err) {
      dispatchApiError(err.message || 'Failed to create workflow')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal onClose={onClose} title="New Workflow" width={400}>
      <form onSubmit={submit}>
        <label htmlFor="dash-wf-name" style={F.label}>Name *</label>
        <input id="dash-wf-name" style={F.input} value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Customer Support Triage" autoFocus />
        <label htmlFor="dash-wf-desc" style={F.label}>Description</label>
        <input id="dash-wf-desc" style={F.input} value={desc} onChange={e=>setDesc(e.target.value)} placeholder="Optional" />
        <ModalFooter onCancel={onClose} submitLabel={loading ? '...' : 'Create'} disabled={loading || !name.trim()} />
      </form>
    </Modal>
  )
}
