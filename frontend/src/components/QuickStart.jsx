import { useState, useEffect } from 'react'
import { api, dispatchApiError } from '../api.js'
import PageHeader from './ui/PageHeader.jsx'
import { pageStyle, panel, panelHeader, btnPrimary } from './ui/styles.js'

// ── Styles ──────────────────────────────────────────────────────────────────

const S = {
  section: {
    marginBottom: 24,
  },
  stepNumber: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 28, height: 28, borderRadius: '50%',
    background: 'rgba(123,164,247,0.15)', color: 'var(--accent)',
    fontSize: 13, fontWeight: 700, flexShrink: 0,
  },
  stepNumberGreen: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 28, height: 28, borderRadius: '50%',
    background: 'rgba(74,222,128,0.15)', color: 'var(--green)',
    fontSize: 13, fontWeight: 700, flexShrink: 0,
  },
  stepHeader: {
    display: 'flex', alignItems: 'center', gap: 12,
    marginBottom: 12,
  },
  stepTitle: {
    fontSize: 15, fontWeight: 600, color: 'var(--text)',
  },
  stepDesc: {
    fontSize: 13, color: 'var(--muted)', lineHeight: 1.6,
    marginBottom: 12, paddingLeft: 40,
  },
  codeBlock: {
    background: 'var(--surface2)', border: '1px solid var(--border)',
    borderRadius: 8, padding: '14px 16px', marginLeft: 40,
    fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.7,
    color: 'var(--text)', overflow: 'auto', position: 'relative',
    whiteSpace: 'pre', wordBreak: 'break-word',
  },
  copyBtn: {
    position: 'absolute', top: 8, right: 8,
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 4, padding: '3px 10px', fontSize: 11,
    color: 'var(--muted)', cursor: 'pointer',
  },
  keyBadge: {
    display: 'inline-block', fontFamily: 'var(--mono)', fontSize: 12,
    background: 'rgba(74,222,128,0.1)', color: 'var(--green)',
    padding: '4px 10px', borderRadius: 4, fontWeight: 600,
    border: '1px solid rgba(74,222,128,0.2)',
  },
  genRow: {
    display: 'flex', alignItems: 'center', gap: 12,
    paddingLeft: 40, marginBottom: 8,
  },
  inlineLink: {
    color: 'var(--accent)', cursor: 'pointer', background: 'none',
    border: 'none', fontSize: 13, padding: 0, textDecoration: 'underline',
    fontFamily: 'var(--font)',
  },
  tipBox: {
    background: 'rgba(123,164,247,0.06)', border: '1px solid rgba(123,164,247,0.15)',
    borderRadius: 8, padding: '12px 16px', marginTop: 20,
    fontSize: 12, color: 'var(--muted)', lineHeight: 1.6,
  },
  tipLabel: {
    fontWeight: 700, color: 'var(--accent)', marginRight: 6,
  },
  // Tab styles
  tabBar: {
    display: 'flex', gap: 0, marginBottom: 24,
    borderBottom: '2px solid var(--border)',
  },
  tab: (active) => ({
    padding: '10px 20px', fontSize: 14, fontWeight: active ? 600 : 400,
    color: active ? 'var(--accent)' : 'var(--muted)',
    background: 'none', border: 'none', cursor: 'pointer',
    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
    marginBottom: -2, transition: 'all 0.15s',
    fontFamily: 'var(--font)',
  }),
  tabBadge: {
    display: 'inline-block', fontSize: 10, fontWeight: 700,
    background: 'var(--green)', color: 'var(--bg)',
    padding: '1px 6px', borderRadius: 4, marginLeft: 8,
    verticalAlign: 'middle',
  },
  actionBtn: (primary) => ({
    ...btnPrimary, fontSize: 13, padding: '10px 20px',
    ...(primary ? {} : {
      background: 'var(--surface)', color: 'var(--accent)',
      border: '1px solid var(--border)',
    }),
  }),
}

function CopyableCode({ code }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div style={S.codeBlock}>
      <button style={S.copyBtn} onClick={copy}>
        {copied ? 'Copied!' : 'Copy'}
      </button>
      {code}
    </div>
  )
}


// ── No-code track ───────────────────────────────────────────────────────────

function NoCodeTrack({ nav }) {
  return (
    <>
      {/* Step 1: Try a Demo */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumberGreen}>1</span>
            <span style={S.stepTitle}>Try a Demo</span>
          </div>
          <div style={S.stepDesc}>
            Load sample data to see how Forkmark works. No API key or setup needed — just click
            and explore real comparisons, decisions, and dashboard charts.
          </div>
          <div style={S.genRow}>
            <button style={S.actionBtn(true)} onClick={() => nav('demos')}>
              Open Demo Gallery
            </button>
          </div>
        </div>
      </div>

      {/* Step 2: Run a Comparison */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumberGreen}>2</span>
            <span style={S.stepTitle}>Run Your First Comparison</span>
          </div>
          <div style={S.stepDesc}>
            Pick two models, write a prompt, and add a few test inputs. Forkmark runs both
            models side-by-side and shows you the results. No code required.
          </div>
          <div style={S.genRow}>
            <button style={S.actionBtn(true)} onClick={() => nav('builder')}>
              Open Run Comparison
            </button>
          </div>
        </div>
      </div>

      {/* Step 3: Review */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumberGreen}>3</span>
            <span style={S.stepTitle}>Review the Results</span>
          </div>
          <div style={S.stepDesc}>
            See both outputs side-by-side. Use keyboard shortcuts (A / B / N) to quickly pick a winner,
            set your confidence level (H / M / L), and add a short rationale. It takes seconds per comparison.
          </div>
          <div style={S.genRow}>
            <button style={S.actionBtn(true)} onClick={() => nav('evalRuns')}>
              View Results
            </button>
          </div>
        </div>
      </div>

      {/* Step 4: Dashboard */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumberGreen}>4</span>
            <span style={S.stepTitle}>Check Your Dashboard</span>
          </div>
          <div style={S.stepDesc}>
            The Dashboard shows an overview of all your comparisons — divergence distribution,
            costs over time, and how many decisions you've made. It updates in real time.
          </div>
          <div style={S.genRow}>
            <button style={S.actionBtn(true)} onClick={() => nav('dashboard')}>
              Go to Dashboard
            </button>
          </div>
        </div>
      </div>

      <div style={S.tipBox}>
        <span style={S.tipLabel}>What's next?</span>
        Once you're comfortable with the review flow, you can export your decisions as DPO training data
        from any Results page — one click to download structured preference pairs for fine-tuning.
      </div>
    </>
  )
}


// ── Developer track ─────────────────────────────────────────────────────────

function DeveloperTrack({ nav }) {
  const [apiKey, setApiKey] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [host, setHost] = useState('http://localhost:7700')

  useEffect(() => {
    if (typeof window !== 'undefined' && window.location.origin) {
      setHost(window.location.origin)
    }
  }, [])

  async function generateKey() {
    setGenerating(true)
    try {
      const result = await api.createKey({ label: 'quickstart' })
      if (result?.raw_key) {
        setApiKey(result.raw_key)
        window.dispatchEvent(new CustomEvent('fp:apisuccess', {
          detail: { message: 'API key created — save it now, it won\'t be shown again.' }
        }))
      }
    } catch (e) {
      dispatchApiError(e.message || 'Failed to create key')
    } finally {
      setGenerating(false)
    }
  }

  const sdkSnippet = `from forkmark import ForkmarkClient

fp = ForkmarkClient("${host}", api_key="${apiKey || 'fm_...'}")

# Log a comparison from your pipeline
with fp.eval_run("my-workflow", "gpt-4o vs claude-sonnet") as run:
    run.compare(
        input="Summarize this contract clause...",
        branch_a={"model": "gpt-4o",           "output": response_a},
        branch_b={"model": "claude-3.5-sonnet", "output": response_b},
    )`

  const installSnippet = `pip install forkmark`

  return (
    <>
      {/* Step 1 */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumber}>1</span>
            <span style={S.stepTitle}>Generate an API Key</span>
          </div>
          <div style={S.stepDesc}>
            API keys authenticate SDK calls. Create one here or manage them in Settings.
          </div>
          {apiKey ? (
            <div style={{ paddingLeft: 40, marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>Your key (save it — shown only once):</div>
              <span style={S.keyBadge}>{apiKey}</span>
            </div>
          ) : (
            <div style={S.genRow}>
              <button style={S.actionBtn(true)}
                      onClick={generateKey} disabled={generating}>
                {generating ? 'Creating...' : 'Generate Key'}
              </button>
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                or <button style={S.inlineLink} onClick={() => nav('keys')}>manage existing keys</button>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Step 2 */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumber}>2</span>
            <span style={S.stepTitle}>Install the SDK</span>
          </div>
          <div style={S.stepDesc}>
            Install the Python SDK from PyPI:
          </div>
          <CopyableCode code={installSnippet} />
        </div>
      </div>

      {/* Step 3 */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumber}>3</span>
            <span style={S.stepTitle}>Log Your First Comparison</span>
          </div>
          <div style={S.stepDesc}>
            Add 5 lines to your existing pipeline. The SDK handles workflow creation, branching, and scoring automatically.
          </div>
          <CopyableCode code={sdkSnippet} />
        </div>
      </div>

      {/* Step 4 */}
      <div style={S.section}>
        <div style={{ ...panel, padding: '20px 24px' }}>
          <div style={S.stepHeader}>
            <span style={S.stepNumber}>4</span>
            <span style={S.stepTitle}>Review and Export</span>
          </div>
          <div style={S.stepDesc}>
            Open the Dashboard to see your comparisons appear. Review outputs side-by-side, record decisions,
            then export DPO training data from any Results batch.
          </div>
          <div style={S.genRow}>
            <button style={S.actionBtn(true)} onClick={() => nav('dashboard')}>
              Go to Dashboard
            </button>
            <button style={S.actionBtn(false)} onClick={() => nav('playground')}>
              Try Playground
            </button>
          </div>
        </div>
      </div>

      <div style={S.tipBox}>
        <span style={S.tipLabel}>Tip:</span>
        No API key needed to explore. Load demo data from the{' '}
        <button style={S.inlineLink} onClick={() => nav('demos')}>Demo Gallery</button>{' '}
        to see the full review workflow without any external LLM calls.
      </div>
    </>
  )
}


// ── Main component ──────────────────────────────────────────────────────────

export default function QuickStart({ nav }) {
  const [track, setTrack] = useState('nocode')

  return (
    <div style={pageStyle(800)}>
      <PageHeader
        title="Quick Start"
        subtitle="Get up and running in under 5 minutes — no coding required."
      />

      {/* Tab bar */}
      <div style={S.tabBar}>
        <button style={S.tab(track === 'nocode')} onClick={() => setTrack('nocode')}>
          No-Code
          <span style={S.tabBadge}>Start here</span>
        </button>
        <button style={S.tab(track === 'developer')} onClick={() => setTrack('developer')}>
          Developer
        </button>
      </div>

      {track === 'nocode'
        ? <NoCodeTrack nav={nav} />
        : <DeveloperTrack nav={nav} />
      }
    </div>
  )
}
