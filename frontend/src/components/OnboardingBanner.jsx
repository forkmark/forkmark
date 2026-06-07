import { useState, useEffect } from 'react'
import { api } from '../api.js'

/**
 * OnboardingBanner — a gentle top-of-page checklist that guides
 * first-time users through: Demo → Run Comparison → Review → Dashboard.
 *
 * Self-dismisses once all steps are done, or if the user clicks "Dismiss".
 * State persisted in sessionStorage so it doesn't nag across sessions.
 */

const STORAGE_KEY = 'fm_onboarding'

const STEPS = [
  { id: 'demo',    label: 'Try a demo',           view: 'demos',    desc: 'Load sample data to explore' },
  { id: 'run',     label: 'Run a comparison',      view: 'builder',  desc: 'Compare two models side-by-side' },
  { id: 'review',  label: 'Review results',        view: 'evalRuns', desc: 'See your comparison batches' },
  { id: 'dash',    label: 'Check your dashboard',  view: 'dashboard',desc: 'View scores and activity' },
]

function loadState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return { dismissed: false, completed: [] }
}

function saveState(state) {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch {}
}

const S = {
  banner: {
    background: 'linear-gradient(135deg, rgba(123,164,247,0.08), rgba(196,161,245,0.08))',
    border: '1px solid rgba(123,164,247,0.2)',
    borderRadius: 0,
    padding: '12px 20px',
    display: 'flex', alignItems: 'center', gap: 16,
    fontSize: 13, color: 'var(--text)',
    borderBottom: '1px solid var(--border)',
  },
  title: {
    fontWeight: 700, fontSize: 13, color: 'var(--accent)',
    whiteSpace: 'nowrap', flexShrink: 0,
  },
  steps: {
    display: 'flex', gap: 6, flex: 1, overflow: 'auto',
  },
  step: (done, active) => ({
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '5px 12px', borderRadius: 20,
    background: done ? 'rgba(74,222,128,0.12)' : active ? 'rgba(123,164,247,0.12)' : 'rgba(107,115,148,0.08)',
    border: `1px solid ${done ? 'rgba(74,222,128,0.3)' : active ? 'rgba(123,164,247,0.3)' : 'transparent'}`,
    color: done ? 'var(--green)' : active ? 'var(--accent)' : 'var(--muted)',
    fontSize: 12, fontWeight: done || active ? 600 : 400,
    cursor: done ? 'default' : 'pointer',
    whiteSpace: 'nowrap', transition: 'all 0.15s',
    textDecoration: done ? 'line-through' : 'none',
  }),
  check: { fontSize: 11 },
  dismiss: {
    background: 'none', border: 'none', color: 'var(--muted)',
    cursor: 'pointer', fontSize: 16, padding: '0 4px', flexShrink: 0,
    opacity: 0.6,
  },
  progress: {
    fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap', flexShrink: 0,
  },
}

export default function OnboardingBanner({ currentView, nav }) {
  const [state, setState] = useState(loadState)
  const [isNewUser, setIsNewUser] = useState(false)

  // Detect if this is a new user (no workflows, no eval runs)
  useEffect(() => {
    if (state.dismissed) return
    Promise.all([api.listWorkflows(), api.listEvalRuns()])
      .then(([wfs, ers]) => {
        const hasData = (wfs?.length || 0) > 0 || (ers?.length || 0) > 0
        setIsNewUser(!hasData)
      })
      .catch(() => setIsNewUser(true))
  }, [state.dismissed])

  // Track completed steps based on which views the user visits
  useEffect(() => {
    const viewToStep = { demos: 'demo', builder: 'run', evalRuns: 'review', evalRunDetail: 'review', compare: 'review', dashboard: 'dash' }
    const stepId = viewToStep[currentView]
    if (stepId && !state.completed.includes(stepId)) {
      const next = { ...state, completed: [...state.completed, stepId] }
      setState(next)
      saveState(next)
    }
  }, [currentView]) // eslint-disable-line react-hooks/exhaustive-deps

  function dismiss() {
    const next = { ...state, dismissed: true }
    setState(next)
    saveState(next)
  }

  // Don't show if dismissed, not a new user, or all steps complete
  if (state.dismissed || !isNewUser) return null
  if (state.completed.length >= STEPS.length) return null

  const doneCount = state.completed.length
  const nextStep = STEPS.find(s => !state.completed.includes(s.id))

  return (
    <div style={S.banner}>
      <span style={S.title}>Getting Started</span>
      <div style={S.steps}>
        {STEPS.map(s => {
          const done = state.completed.includes(s.id)
          const active = !done && s.id === nextStep?.id
          return (
            <button
              key={s.id}
              style={S.step(done, active)}
              onClick={() => !done && nav(s.view)}
              title={s.desc}
              disabled={done}
            >
              <span style={S.check}>{done ? '✓' : active ? '→' : '○'}</span>
              {s.label}
            </button>
          )
        })}
      </div>
      <span style={S.progress}>{doneCount}/{STEPS.length}</span>
      <button style={S.dismiss} onClick={dismiss} title="Dismiss onboarding" aria-label="Dismiss onboarding">×</button>
    </div>
  )
}
