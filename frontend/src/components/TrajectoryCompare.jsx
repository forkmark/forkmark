/**
 * TrajectoryCompare — Agent trajectory comparison view.
 *
 * Renders a side-by-side timeline of two agent trajectories (trace events)
 * with trajectory scoring breakdown (tool sequence, outcome equivalence,
 * efficiency). Feature-gated: only renders when agent comparison is enabled.
 *
 * Routes: #agentCompare?compId=xxx
 */

import { useState, useEffect, useCallback } from 'react'

const BASE = '/api'

async function fetchJSON(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── Styles ──────────────────────────────────────────────────────────────────

const S = {
  container: { padding: '24px 32px', maxWidth: 1400, margin: '0 auto' },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 24,
  },
  title: { fontSize: 20, fontWeight: 700, color: 'var(--fg)' },
  subtitle: { fontSize: 13, color: 'var(--muted)', marginTop: 4 },
  badge: {
    display: 'inline-block', padding: '3px 10px', borderRadius: 12,
    fontSize: 11, fontWeight: 600, letterSpacing: 0.5,
    background: 'var(--accent)', color: 'var(--bg)',
  },

  // Score cards
  scoreRow: {
    display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16,
    marginBottom: 24,
  },
  scoreCard: (highlight) => ({
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, padding: '16px 20px', textAlign: 'center',
    ...(highlight ? { borderColor: 'var(--accent)', boxShadow: '0 0 0 1px var(--accent)' } : {}),
  }),
  scoreLabel: { fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  scoreValue: (v) => ({
    fontSize: 28, fontWeight: 700,
    color: v >= 0.8 ? 'var(--green)' : v >= 0.5 ? 'var(--yellow, var(--accent))' : 'var(--red)',
  }),

  // Timeline columns
  columns: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 },
  column: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, overflow: 'hidden',
  },
  colHeader: (isBaseline) => ({
    padding: '12px 16px', fontWeight: 600, fontSize: 13,
    borderBottom: '1px solid var(--border)',
    background: isBaseline ? 'rgba(99,102,241,0.08)' : 'rgba(236,72,153,0.08)',
    color: isBaseline ? 'var(--accent)' : 'var(--pink, var(--red))',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  }),
  eventList: { padding: 0, margin: 0, listStyle: 'none' },
  eventItem: (depth) => ({
    padding: '10px 16px', paddingLeft: 16 + depth * 20,
    borderBottom: '1px solid var(--border)',
    fontSize: 13, display: 'flex', alignItems: 'center', gap: 10,
    cursor: 'pointer', transition: 'background 0.15s',
  }),
  eventDot: (type) => ({
    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
    background: {
      reasoning: '#818cf8', tool_call: '#34d399', tool_result: '#60a5fa',
      sub_agent: '#f472b6', observation: '#fbbf24', decision: '#a78bfa',
      error: '#ef4444',
    }[type] || '#6b7280',
  }),
  eventName: { fontWeight: 500, flex: 1 },
  eventMeta: { color: 'var(--muted)', fontSize: 11, whiteSpace: 'nowrap' },

  // Detail panel
  detailPanel: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, padding: 20, marginBottom: 24,
  },
  detailTitle: { fontSize: 14, fontWeight: 600, marginBottom: 12, color: 'var(--fg)' },
  detailGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 },
  detailLabel: { fontSize: 11, color: 'var(--muted)', marginBottom: 4 },
  detailValue: { fontSize: 13, color: 'var(--fg)' },
  json: {
    background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6,
    padding: 12, fontSize: 12, fontFamily: 'monospace', whiteSpace: 'pre-wrap',
    wordBreak: 'break-all', maxHeight: 200, overflow: 'auto', color: 'var(--fg)',
  },

  // Empty state
  empty: {
    textAlign: 'center', padding: 60, color: 'var(--muted)', fontSize: 14,
  },
  loading: { textAlign: 'center', padding: 60, color: 'var(--muted)', fontSize: 13 },
  error: { textAlign: 'center', padding: 60, color: 'var(--red)', fontSize: 13 },

  // Stats row
  statsRow: {
    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16,
    marginBottom: 24,
  },
  statCard: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, padding: '14px 20px',
  },
  statLabel: { fontSize: 11, color: 'var(--muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  statPair: { display: 'flex', justifyContent: 'space-between', gap: 20 },
  statValue: { fontSize: 15, fontWeight: 600, color: 'var(--fg)' },
  statSide: { fontSize: 11, color: 'var(--muted)' },
}


// ── Helper: build tree from flat events ─────────────────────────────────────

function buildTree(events) {
  const roots = []
  const childMap = {}
  for (const ev of events) {
    const pid = ev.parent_event_id || '__root__'
    if (!childMap[pid]) childMap[pid] = []
    childMap[pid].push(ev)
  }
  function flatten(parentId, depth) {
    const children = (childMap[parentId] || []).sort((a, b) => a.event_index - b.event_index)
    const result = []
    for (const ch of children) {
      result.push({ ...ch, _depth: depth })
      result.push(...flatten(ch.id, depth + 1))
    }
    return result
  }
  return flatten('__root__', 0)
}

function fmtMs(ms) {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtCost(usd) {
  if (!usd) return '—'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(3)}`
}

function scorePercent(v) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
}


// ── Main component ──────────────────────────────────────────────────────────

export default function TrajectoryCompare({ compId, nav }) {
  const [outcome, setOutcome] = useState(null)
  const [eventsA, setEventsA] = useState([])
  const [eventsB, setEventsB] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [featureEnabled, setFeatureEnabled] = useState(true)

  useEffect(() => {
    if (!compId) return
    setLoading(true)
    setError(null)

    // Check feature status first
    fetchJSON('/agent/feature-status')
      .then(d => setFeatureEnabled(d.enabled))
      .catch(() => setFeatureEnabled(false))

    // Fetch trajectory outcome
    fetchJSON(`/agent/trajectory/${compId}`)
      .then(data => {
        setOutcome(data)
        // Now fetch events for both branches
        const comp = fetchJSON(`/comparisons/${compId}`)
        return comp
      })
      .then(comp => {
        return Promise.all([
          fetchJSON(`/agent/trace-events?branch_id=${comp.branch_a_id}`),
          fetchJSON(`/agent/trace-events?branch_id=${comp.branch_b_id}`),
        ])
      })
      .then(([a, b]) => {
        setEventsA(buildTree(a))
        setEventsB(buildTree(b))
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [compId])

  if (!featureEnabled) {
    return (
      <div style={S.empty}>
        <div style={{ fontSize: 32, marginBottom: 12, opacity: 0.3 }}>Agent Comparison</div>
        <div>Agent comparison is not enabled. Set <code>FM_ENABLE_AGENT_COMPARISON=true</code> to activate.</div>
      </div>
    )
  }

  if (loading) return <div style={S.loading}>Loading trajectory data...</div>
  if (error) return <div style={S.error}>Error: {error}</div>
  if (!outcome) return <div style={S.empty}>No trajectory data found for this comparison.</div>

  return (
    <div style={S.container}>
      {/* Header */}
      <div style={S.header}>
        <div>
          <div style={S.title}>Agent Trajectory Comparison</div>
          <div style={S.subtitle}>Comparison {compId}</div>
        </div>
        <span style={S.badge}>AGENT RUN</span>
      </div>

      {/* Score cards */}
      <div style={S.scoreRow}>
        <div style={S.scoreCard(true)}>
          <div style={S.scoreLabel}>Overall Score</div>
          <div style={S.scoreValue(outcome.trajectory_score)}>
            {scorePercent(outcome.trajectory_score)}
          </div>
        </div>
        <div style={S.scoreCard(false)}>
          <div style={S.scoreLabel}>Tool Sequence</div>
          <div style={S.scoreValue(outcome.tool_sequence_score)}>
            {scorePercent(outcome.tool_sequence_score)}
          </div>
        </div>
        <div style={S.scoreCard(false)}>
          <div style={S.scoreLabel}>Outcome Equivalence</div>
          <div style={S.scoreValue(outcome.outcome_equivalence_score)}>
            {scorePercent(outcome.outcome_equivalence_score)}
          </div>
        </div>
        <div style={S.scoreCard(false)}>
          <div style={S.scoreLabel}>Efficiency</div>
          <div style={S.scoreValue(outcome.efficiency_score)}>
            {scorePercent(outcome.efficiency_score)}
          </div>
        </div>
      </div>

      {/* Stats comparison */}
      <div style={S.statsRow}>
        <div style={S.statCard}>
          <div style={S.statLabel}>Tool Calls</div>
          <div style={S.statPair}>
            <div>
              <div style={S.statValue}>{outcome.branch_a_tool_count}</div>
              <div style={S.statSide}>Branch A</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={S.statValue}>{outcome.branch_b_tool_count}</div>
              <div style={S.statSide}>Branch B</div>
            </div>
          </div>
        </div>
        <div style={S.statCard}>
          <div style={S.statLabel}>Total Latency</div>
          <div style={S.statPair}>
            <div>
              <div style={S.statValue}>{fmtMs(outcome.branch_a_total_latency_ms)}</div>
              <div style={S.statSide}>Branch A</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={S.statValue}>{fmtMs(outcome.branch_b_total_latency_ms)}</div>
              <div style={S.statSide}>Branch B</div>
            </div>
          </div>
        </div>
        <div style={S.statCard}>
          <div style={S.statLabel}>Total Cost</div>
          <div style={S.statPair}>
            <div>
              <div style={S.statValue}>{fmtCost(outcome.branch_a_total_cost_usd)}</div>
              <div style={S.statSide}>Branch A</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={S.statValue}>{fmtCost(outcome.branch_b_total_cost_usd)}</div>
              <div style={S.statSide}>Branch B</div>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline columns */}
      <div style={S.columns}>
        <div style={S.column}>
          <div style={S.colHeader(true)}>
            <span>Branch A (Baseline)</span>
            <span style={{ fontSize: 11, opacity: 0.7 }}>{eventsA.length} events</span>
          </div>
          <ul style={S.eventList}>
            {eventsA.length === 0 && (
              <li style={{ ...S.eventItem(0), color: 'var(--muted)' }}>No trace events recorded</li>
            )}
            {eventsA.map(ev => (
              <li
                key={ev.id}
                style={{
                  ...S.eventItem(ev._depth),
                  background: selectedEvent?.id === ev.id ? 'rgba(99,102,241,0.1)' : 'transparent',
                }}
                onClick={() => setSelectedEvent(selectedEvent?.id === ev.id ? null : ev)}
              >
                <span style={S.eventDot(ev.event_type)} title={ev.event_type} />
                <span style={S.eventName}>{ev.name || ev.event_type}</span>
                <span style={S.eventMeta}>{fmtMs(ev.latency_ms)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div style={S.column}>
          <div style={S.colHeader(false)}>
            <span>Branch B (Challenger)</span>
            <span style={{ fontSize: 11, opacity: 0.7 }}>{eventsB.length} events</span>
          </div>
          <ul style={S.eventList}>
            {eventsB.length === 0 && (
              <li style={{ ...S.eventItem(0), color: 'var(--muted)' }}>No trace events recorded</li>
            )}
            {eventsB.map(ev => (
              <li
                key={ev.id}
                style={{
                  ...S.eventItem(ev._depth),
                  background: selectedEvent?.id === ev.id ? 'rgba(236,72,153,0.1)' : 'transparent',
                }}
                onClick={() => setSelectedEvent(selectedEvent?.id === ev.id ? null : ev)}
              >
                <span style={S.eventDot(ev.event_type)} title={ev.event_type} />
                <span style={S.eventName}>{ev.name || ev.event_type}</span>
                <span style={S.eventMeta}>{fmtMs(ev.latency_ms)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Event detail panel */}
      {selectedEvent && (
        <div style={S.detailPanel}>
          <div style={S.detailTitle}>
            Event: {selectedEvent.name}
            <span style={{ ...S.badge, marginLeft: 10, fontSize: 10 }}>
              {selectedEvent.event_type}
            </span>
          </div>
          <div style={S.detailGrid}>
            <div>
              <div style={S.detailLabel}>Status</div>
              <div style={S.detailValue}>{selectedEvent.status}</div>
            </div>
            <div>
              <div style={S.detailLabel}>Latency</div>
              <div style={S.detailValue}>{fmtMs(selectedEvent.latency_ms)}</div>
            </div>
            <div>
              <div style={S.detailLabel}>Tokens (in / out)</div>
              <div style={S.detailValue}>
                {selectedEvent.tokens_input || 0} / {selectedEvent.tokens_output || 0}
              </div>
            </div>
            <div>
              <div style={S.detailLabel}>Cost</div>
              <div style={S.detailValue}>{fmtCost(selectedEvent.cost_usd)}</div>
            </div>
          </div>
          {selectedEvent.input_data && Object.keys(selectedEvent.input_data).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={S.detailLabel}>Input</div>
              <pre style={S.json}>{JSON.stringify(selectedEvent.input_data, null, 2)}</pre>
            </div>
          )}
          {selectedEvent.output_data && Object.keys(selectedEvent.output_data).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={S.detailLabel}>Output</div>
              <pre style={S.json}>{JSON.stringify(selectedEvent.output_data, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
