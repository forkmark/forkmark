import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import Sidebar from './components/Sidebar.jsx'
import OnboardingBanner from './components/OnboardingBanner.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { api, enrichErrorMessage } from './api.js'

// Lazy-loaded views — only downloaded when first navigated to
const Dashboard       = lazy(() => import('./components/Dashboard.jsx'))
const EvalRuns        = lazy(() => import('./components/EvalRuns.jsx'))
const EvalRunDetail   = lazy(() => import('./components/EvalRunDetail.jsx'))
const TestSets        = lazy(() => import('./components/TestSets.jsx'))
const WorkflowDetail  = lazy(() => import('./components/WorkflowDetail.jsx'))
const BranchCompare   = lazy(() => import('./components/BranchCompare.jsx'))
const DecisionHistory = lazy(() => import('./components/DecisionHistory.jsx'))
const ApiKeys         = lazy(() => import('./components/ApiKeys.jsx'))
const Settings        = lazy(() => import('./components/Settings.jsx'))
const WorkflowBuilder = lazy(() => import('./components/WorkflowBuilder.jsx'))
const ReviewQueue     = lazy(() => import('./components/ReviewQueue.jsx'))
const Playground      = lazy(() => import('./components/Playground.jsx'))
const TracingDashboard= lazy(() => import('./components/TracingDashboard.jsx'))
const DemoGallery     = lazy(() => import('./components/DemoGallery.jsx'))
const QuickStart      = lazy(() => import('./components/QuickStart.jsx'))
const TrajectoryCompare = lazy(() => import('./components/TrajectoryCompare.jsx'))

const VALID_VIEWS = new Set([
  'dashboard','evalRuns','evalRunDetail','testSets','workflow',
  'compare','history','keys','settings','builder','reviewQueue',
  'playground','tracing','demos','quickstart','agentCompare',
])

// Hash-based routing — each view is encoded as #view[?key=val&key=val]
// e.g. #workflow?workflowId=abc123
//      #compare?compId=xyz&evalRunId=er1

const S = {
  app:  { display:'flex', height:'100vh', overflow:'hidden' },
  main: { flex:1, overflow:'auto', background:'var(--bg)' },
  skipNav: {
    position:'absolute', left:'-9999px', top:'auto', width:'1px', height:'1px',
    overflow:'hidden', zIndex:10000,
    // Becomes visible on focus:
  },
  skipNavFocus: {
    position:'fixed', top:8, left:8, zIndex:10000,
    padding:'8px 16px', background:'var(--accent)', color:'var(--bg)',
    borderRadius:6, fontSize:13, fontWeight:700, textDecoration:'none',
    boxShadow:'0 2px 8px rgba(0,0,0,0.4)',
  },

  // Toast styles
  toastWrap: {
    position:'fixed', bottom:24, right:24, zIndex:9999,
    display:'flex', flexDirection:'column', gap:8,
    pointerEvents:'none',
  },
  toast: (type) => ({
    padding:'10px 16px', borderRadius:8, fontSize:13, fontWeight:500,
    maxWidth:380, pointerEvents:'all',
    background: 'var(--surface)',
    border: `1px solid ${
      type === 'error'   ? 'var(--red)'
    : type === 'success' ? 'var(--green)'
    :                      'var(--accent)'}`,
    color: type === 'error'   ? 'var(--red)'
         : type === 'success' ? 'var(--green)'
         : 'var(--accent)',
    boxShadow:'0 4px 12px rgba(0,0,0,0.4)',
    display:'flex', alignItems:'center', gap:10,
  }),
  toastIcon: { fontSize:16, flexShrink:0 },
  toastClose: {
    marginLeft:'auto', background:'none', border:'none',
    color:'inherit', opacity:0.6, cursor:'pointer', fontSize:16, padding:'0 0 0 8px',
  },
}

// ── Skip-nav link (visible only on focus for keyboard users) ─────────────────

function SkipNav() {
  const [focused, setFocused] = useState(false)
  return (
    <a
      href="#main-content"
      style={focused ? S.skipNavFocus : S.skipNav}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    >
      Skip to main content
    </a>
  )
}

// ── Lazy loading fallback ─────────────────────────────────────────────────────

const loadingFallback = (
  <div style={{ padding: 40, color: 'var(--muted)', fontSize: 13 }}>Loading…</div>
)

// ── 404 page ─────────────────────────────────────────────────────────────────

function NotFound({ view }) {
  return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>404</div>
      <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Page not found</div>
      <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 20 }}>
        The view <code style={{ color: 'var(--accent)' }}>#{view}</code> doesn't exist.
      </div>
      <a href="#dashboard" style={{ fontSize: 13, color: 'var(--accent)' }}>← Back to Dashboard</a>
    </div>
  )
}

// ── Toast manager ─────────────────────────────────────────────────────────────

let _toastId = 0

function Toast({ id, message, type, action, onDismiss }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(id), action ? 8000 : 5000)
    return () => clearTimeout(t)
  }, [id, onDismiss, action])

  const icons = { error: '✕', success: '✓', info: 'ℹ' }
  return (
    <div style={S.toast(type)}>
      <span style={S.toastIcon}>{icons[type] || 'ℹ'}</span>
      <span>
        {message}
        {action?.label && action?.hash && (
          <>
            {' '}
            <a href={action.hash} style={{
              color: 'inherit', fontWeight: 600, textDecoration: 'underline',
              cursor: 'pointer',
            }}>
              {action.label} →
            </a>
          </>
        )}
      </span>
      <button style={S.toastClose} onClick={() => onDismiss(id)} aria-label="Dismiss notification">×</button>
    </div>
  )
}

// ── Hash routing helpers ──────────────────────────────────────────────────────

function parseHash() {
  const raw = window.location.hash.slice(1)
  const [view, qs] = raw.split('?')
  const params = {}
  if (qs) {
    for (const part of qs.split('&')) {
      const [k, v] = part.split('=')
      if (k) params[decodeURIComponent(k)] = decodeURIComponent(v || '')
    }
  }
  return { view: view || 'dashboard', params }
}

function buildHash(view, params = {}) {
  const qs = Object.entries(params)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
  return '#' + view + (qs ? '?' + qs : '')
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [state,  setState]  = useState(() => parseHash())
  const [toasts, setToasts] = useState([])
  const [enterpriseMode, setEnterpriseMode] = useState(false)
  const [agentEnabled, setAgentEnabled] = useState(false)

  // Detect enterprise mode from system info + agent feature status
  useEffect(() => {
    api.getSystemInfo().then(info => {
      setEnterpriseMode(info.multi_tenant || false)
    }).catch(() => {})
    api.agentFeatureStatus().then(info => {
      setAgentEnabled(info.enabled || false)
    }).catch(() => {})
  }, [])

  // Keep state in sync with browser hash navigation (back/forward)
  useEffect(() => {
    function onHashChange() { setState(parseHash()) }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Global API error listener — any component can fire 'fp:apierror'
  useEffect(() => {
    function onApiError(e) {
      const msg = e.detail?.message || 'An unexpected error occurred'
      const explicitAction = e.detail?.action
      const enriched = enrichErrorMessage(msg)
      const action = explicitAction || enriched.action
      setToasts(ts => [...ts, { id: ++_toastId, message: enriched.message || msg, type: 'error', action }])
    }
    function onApiSuccess(e) {
      const msg = e.detail?.message
      if (msg) setToasts(ts => [...ts, { id: ++_toastId, message: msg, type: 'success' }])
    }
    window.addEventListener('fp:apierror',   onApiError)
    window.addEventListener('fp:apisuccess', onApiSuccess)
    return () => {
      window.removeEventListener('fp:apierror',   onApiError)
      window.removeEventListener('fp:apisuccess', onApiSuccess)
    }
  }, [])

  const dismissToast = useCallback((id) => {
    setToasts(ts => ts.filter(t => t.id !== id))
  }, [])

  function nav(view, extra = {}) {
    const params = {}
    if (extra.evalRunId  != null) params.evalRunId  = extra.evalRunId
    if (extra.workflowId != null) params.workflowId = extra.workflowId
    if (extra.compId     != null) params.compId     = extra.compId
    window.location.hash = buildHash(view, params)
  }

  const { view, params } = state

  return (
    <div style={S.app}>
      <SkipNav />
      <Sidebar active={view} nav={nav} enterpriseMode={enterpriseMode} agentEnabled={agentEnabled} />
      <main id="main-content" style={S.main} tabIndex={-1}>
        <OnboardingBanner currentView={view} nav={nav} />
        <Suspense fallback={loadingFallback}>
          {!VALID_VIEWS.has(view) ? (
            <NotFound view={view} />
          ) : (
            <>
              <ErrorBoundary label="Dashboard" key={'dashboard-' + (view === 'dashboard')}>
                {view === 'dashboard'     && <Dashboard nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Eval Runs" key={'evalRuns-' + (view === 'evalRuns')}>
                {view === 'evalRuns'      && <EvalRuns nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Eval Run Detail" key={'evalRunDetail-' + params.evalRunId}>
                {view === 'evalRunDetail' && <EvalRunDetail evalRunId={params.evalRunId} nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Test Sets" key={'testSets-' + (view === 'testSets')}>
                {view === 'testSets'      && <TestSets nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Workflow Detail" key={'workflow-' + params.workflowId}>
                {view === 'workflow'      && <WorkflowDetail workflowId={params.workflowId} nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Comparison" key={'compare-' + params.compId}>
                {view === 'compare'       && <BranchCompare compId={params.compId} nav={nav} evalRunId={params.evalRunId} />}
              </ErrorBoundary>
              <ErrorBoundary label="Decision History" key={'history-' + params.workflowId}>
                {view === 'history'       && <DecisionHistory workflowId={params.workflowId} nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="API Keys" key={'keys-' + (view === 'keys')}>
                {view === 'keys'          && <ApiKeys />}
              </ErrorBoundary>
              <ErrorBoundary label="Settings" key={'settings-' + (view === 'settings')}>
                {view === 'settings'      && <Settings />}
              </ErrorBoundary>
              <ErrorBoundary label="Workflow Builder" key={'builder-' + (view === 'builder')}>
                {view === 'builder'       && <WorkflowBuilder nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Review Queue" key={'reviewQueue-' + (view === 'reviewQueue')}>
                {view === 'reviewQueue'   && <ReviewQueue nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Playground" key={'playground-' + (view === 'playground')}>
                {view === 'playground'    && <Playground nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Tracing" key={'tracing-' + (view === 'tracing')}>
                {view === 'tracing'       && <TracingDashboard />}
              </ErrorBoundary>
              <ErrorBoundary label="Demo Gallery" key={'demos-' + (view === 'demos')}>
                {view === 'demos'         && <DemoGallery nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Quick Start" key={'quickstart-' + (view === 'quickstart')}>
                {view === 'quickstart'    && <QuickStart nav={nav} />}
              </ErrorBoundary>
              <ErrorBoundary label="Agent Compare" key={'agentCompare-' + params.compId}>
                {view === 'agentCompare'  && <TrajectoryCompare compId={params.compId} nav={nav} />}
              </ErrorBoundary>
            </>
          )}
        </Suspense>
      </main>

      {/* Global toast stack */}
      <div style={S.toastWrap} role="status" aria-live="polite">
        {toasts.map(t => (
          <Toast key={t.id} {...t} onDismiss={dismissToast} />
        ))}
      </div>
    </div>
  )
}
