import { useState, useEffect } from 'react'

// Inline SVG icons (16×16) — replaces Unicode chars for cross-platform consistency
const svg = (d) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display:'block' }}>
    {d}
  </svg>
)

const agentIcon = svg(<><path d="M12 2a4 4 0 014 4v1a1 1 0 001 1h1a4 4 0 010 8h-1a1 1 0 00-1 1v1a4 4 0 01-8 0v-1a1 1 0 00-1-1H6a4 4 0 010-8h1a1 1 0 001-1V6a4 4 0 014-4z"/><circle cx="12" cy="12" r="2"/></>)

const icons = {
  demos:       svg(<><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><path d="M3.27 6.96L12 12.01l8.73-5.05"/><path d="M12 22.08V12"/></>),
  dashboard:   svg(<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>),
  builder:     svg(<polygon points="5 3 19 12 5 21 5 3"/>),
  playground:  svg(<><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></>),
  evalRuns:    svg(<><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></>),
  testSets:    svg(<><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h8"/></>),
  workflow:    svg(<><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 012 2v7"/><path d="M6 9v12"/></>),
  history:     svg(<><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>),
  reviewQueue: svg(<><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></>),
  tracing:     svg(<><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></>),
  keys:        svg(<><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></>),
  settings:    svg(<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></>),
}

const ITEMS = [
  { id:'demos',         label:'Demo Gallery',      icon: icons.demos, primary: true,
    tip:'Try pre-built examples to see Forkmark in action' },
  { id:'dashboard',     label:'Dashboard',         icon: icons.dashboard,
    tip:'Overview of your evaluation activity, scores, and costs' },
  { id:'builder',       label:'Run Comparison',    icon: icons.builder, primary: true,
    tip:'Compare two models or prompts side-by-side — no code needed' },
  { id:'playground',    label:'Playground',        icon: icons.playground,
    tip:'Test a single prompt quickly and see the raw output' },
  { id:'evalRuns',      label:'Results',           icon: icons.evalRuns,
    tip:'Browse your comparison batches and see aggregate scores' },
  { id:'testSets',      label:'Test Inputs',       icon: icons.testSets,
    tip:'Manage reusable sets of test cases for consistent evaluation' },
  { id:'workflow',      label:'Workflows',         icon: icons.workflow,
    tip:'View all registered workflows and their run history' },
  { id:'history',       label:'Past Verdicts',     icon: icons.history,
    tip:'Review every decision you\'ve made, with filters and export' },
  { id:'agentCompare',  label:'Agent Runs',        icon: agentIcon, agentFeature: true,
    tip:'Compare agent trajectories — tool calls, reasoning, and outcomes' },
  { id:'reviewQueue',   label:'Review Queue',      icon: icons.reviewQueue, enterprise: true,
    tip:'See comparisons assigned to you that need a verdict' },
  { id:'tracing',       label:'Observability',     icon: icons.tracing, enterprise: true,
    tip:'Monitor system performance, latency, and trace data' },
  { id:'keys',          label:'API Keys',          icon: icons.keys,
    tip:'Create and manage keys for the SDK and API access' },
  { id:'settings',      label:'Settings',          icon: icons.settings,
    tip:'Configure models, scoring, theme, and infrastructure' },
]

const COLLAPSED_W = 52
const EXPANDED_W  = 220
const BREAKPOINT  = 900

const S = {
  nav: (collapsed) => ({
    width: collapsed ? COLLAPSED_W : EXPANDED_W,
    minWidth: collapsed ? COLLAPSED_W : EXPANDED_W,
    background: 'var(--surface)', borderRight: '1px solid var(--border)',
    display: 'flex', flexDirection: 'column', padding: 0,
    transition: 'width 0.2s ease, min-width 0.2s ease',
    overflow: 'hidden',
  }),
  logo: (collapsed) => ({
    padding: collapsed ? '16px 0' : '20px 16px 12px',
    borderBottom: '1px solid var(--border)',
    fontSize: 18, fontWeight: 800, color: 'var(--accent)', letterSpacing: '-0.04em',
    textAlign: collapsed ? 'center' : 'left',
    whiteSpace: 'nowrap', overflow: 'hidden',
  }),
  sub: { fontSize: 9, color: 'var(--muted)', fontWeight: 500, letterSpacing: '0.12em', textTransform: 'uppercase', display: 'block', marginTop: 3 },
  list: { flex: 1, padding: '8px 0', overflowY: 'auto', overflowX: 'hidden' },
  item: (active, collapsed) => ({
    display: 'flex', alignItems: 'center', gap: collapsed ? 0 : 10,
    padding: collapsed ? '9px 0' : '9px 16px',
    justifyContent: collapsed ? 'center' : 'flex-start',
    cursor: 'pointer', fontSize: 13,
    fontWeight: active ? 600 : 450,
    letterSpacing: '-0.01em',
    color: active ? 'var(--accent)' : 'var(--text)',
    background: active ? 'rgba(123,164,247,0.08)' : 'transparent',
    borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
    transition: 'all 0.15s',
    whiteSpace: 'nowrap', overflow: 'hidden',
    position: 'relative',
  }),
  icon: { width: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  toggle: (collapsed) => ({
    padding: '10px 0', borderTop: '1px solid var(--border)',
    textAlign: 'center', cursor: 'pointer',
    fontSize: 14, color: 'var(--muted)', userSelect: 'none',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  }),
  footer: (collapsed) => ({
    padding: collapsed ? '8px 0' : '12px 16px',
    borderTop: '1px solid var(--border)',
    fontSize: 11, color: 'var(--muted)',
    textAlign: collapsed ? 'center' : 'left',
  }),
  tooltip: {
    position: 'absolute', left: COLLAPSED_W - 4, top: '50%', transform: 'translateY(-50%)',
    background: 'var(--surface2)', border: '1px solid var(--border)',
    padding: '4px 10px', borderRadius: 5, fontSize: 12, fontWeight: 500,
    color: 'var(--text)', whiteSpace: 'nowrap', zIndex: 50,
    pointerEvents: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
  },
  expandedTip: {
    position: 'absolute', left: EXPANDED_W + 8, top: '50%', transform: 'translateY(-50%)',
    background: 'var(--surface2)', border: '1px solid var(--border)',
    padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 400,
    color: 'var(--muted)', whiteSpace: 'nowrap', zIndex: 50,
    pointerEvents: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
    maxWidth: 260,
  },
}

export default function Sidebar({ active, nav, enterpriseMode = false, agentEnabled = false }) {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < BREAKPOINT)
  const [hoveredId, setHoveredId] = useState(null)

  // Auto-collapse on narrow viewports
  useEffect(() => {
    function handleResize() {
      if (window.innerWidth < BREAKPOINT) setCollapsed(true)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Keyboard shortcut: [ to toggle sidebar
  useEffect(() => {
    function handleKey(e) {
      if (e.key === '[' && !e.ctrlKey && !e.metaKey && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        setCollapsed(c => !c)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [])

  const handleItemKey = (e, id) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      nav(id)
    }
  }

  return (
    <nav style={S.nav(collapsed)} aria-label="Main navigation">
      <div style={S.logo(collapsed)}>
        {collapsed ? 'F' : 'Forkmark'}
        {!collapsed && <span style={S.sub}>AI WORKFLOW QA</span>}
      </div>
      <ul style={{ ...S.list, listStyle: 'none' }} role="list">
        {ITEMS.filter(i => (!i.enterprise || enterpriseMode) && (!i.agentFeature || agentEnabled)).map(i => {
          const isActive = active === i.id || (active === 'evalRunDetail' && i.id === 'evalRuns')
          return (
            <li key={i.id}>
              <div
                role="link"
                tabIndex={0}
                style={S.item(isActive, collapsed)}
                onClick={() => nav(i.id)}
                onKeyDown={(e) => handleItemKey(e, i.id)}
                onMouseEnter={() => setHoveredId(i.id)}
                onMouseLeave={() => setHoveredId(null)}
                aria-current={isActive ? 'page' : undefined}
                aria-label={collapsed ? i.label : undefined}
              >
                <span style={S.icon} aria-hidden="true">{i.icon}</span>
                {!collapsed && (
                  <>
                    <span style={{ flex: 1 }}>{i.label}</span>
                    {i.primary && (
                      <span style={{ fontSize: 9, background: 'var(--accent)', color: 'var(--bg)', padding: '1px 5px', borderRadius: 4, fontWeight: 700, letterSpacing: '0.3px' }}>
                        PRIMARY
                      </span>
                    )}
                    {i.enterprise && (
                      <span style={{ fontSize: 9, background: 'var(--purple)', color: '#fff', padding: '1px 5px', borderRadius: 4, fontWeight: 700, letterSpacing: '0.3px' }}>
                        ENT
                      </span>
                    )}
                  </>
                )}
                {hoveredId === i.id && collapsed && (
                  <div style={S.tooltip} role="tooltip">{i.label}</div>
                )}
                {hoveredId === i.id && !collapsed && i.tip && (
                  <div style={S.expandedTip} role="tooltip">{i.tip}</div>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <button
        style={{ ...S.toggle(collapsed), background: 'none', border: 'none', width: '100%', fontFamily: 'inherit' }}
        onClick={() => setCollapsed(c => !c)}
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? '▸' : '◂ Collapse'}
      </button>
      <div style={S.footer(collapsed)}>
        {collapsed ? 'v0.1.1' : <>v0.1.1 · <span style={{ color: enterpriseMode ? 'var(--purple)' : 'var(--green)' }}>{enterpriseMode ? 'Enterprise' : 'Community'}</span></>}
      </div>
    </nav>
  )
}
