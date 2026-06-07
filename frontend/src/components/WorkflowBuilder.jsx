/**
 * WorkflowBuilder — dual-mode workflow runner
 *
 * No-code Mode  : fill in a form, click Run, watch it go
 * Developer Mode: generates a Python SDK snippet to copy
 *
 * Test cases can also be stored as persistent Test Sets (via the Test Sets view).
 */
import { useState, useCallback } from 'react'
import { api, dispatchApiError } from '../api.js'
import {
  PageHeader, InfoTip, pageStyle, panel, btnPrimary, btnSecondary, btnDanger,
} from './ui'

const S = {
  tabs: {
    display:'flex', gap:0, marginBottom:28,
    border:'1px solid var(--border)', borderRadius:8, overflow:'hidden', width:'fit-content',
  },
  tab: (active) => ({
    padding:'9px 20px', fontSize:13, fontWeight: active ? 600 : 400,
    cursor:'pointer', border:'none', outline:'none',
    background: active ? 'var(--accent)' : 'var(--surface)',
    color: active ? 'var(--bg)' : 'var(--text)',
    transition:'all 0.15s',
  }),

  card:   (side) => ({ ...panel, padding:24, marginBottom:20, borderLeft: `3px solid ${side === 'B' ? 'var(--purple)' : 'var(--accent)'}`, borderRadius:'2px 8px 8px 2px' }),
  cardH:  { fontSize:14, fontWeight:700, color:'var(--text)', margin:'0 0 16px 0', display:'flex', alignItems:'center', gap:8, letterSpacing:'-0.01em' },
  badge:  { fontSize:10, padding:'2px 6px', borderRadius:4, background:'rgba(123,164,247,0.15)', color:'var(--accent)', fontWeight:700, letterSpacing:'0.3px' },

  row:    { marginBottom:14 },
  label:  { display:'block', fontSize:11, fontWeight:600, color:'var(--muted)', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.5px' },
  input:  { width:'100%', boxSizing:'border-box', background:'var(--bg)', border:'1px solid var(--border)', borderRadius:6, padding:'8px 11px', fontSize:13, color:'var(--text)', outline:'none' },
  textarea: { width:'100%', boxSizing:'border-box', background:'var(--bg)', border:'1px solid var(--border)', borderRadius:6, padding:'8px 11px', fontSize:12, color:'var(--text)', outline:'none', fontFamily:'monospace', resize:'vertical', minHeight:60 },
  hint:   { fontSize:11, color:'var(--muted)', marginTop:3 },

  twoCol: { display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:14 },
  threeCol: { display:'grid', gridTemplateColumns:'1fr 1fr auto', gap:10, alignItems:'end' },

  stepRow: { background:'var(--bg)', border:'1px solid var(--border)', borderRadius:6, padding:14, marginBottom:10 },
  stepNum: { fontSize:11, fontWeight:700, color:'var(--accent)', marginBottom:8, textTransform:'uppercase', letterSpacing:'0.4px' },

  iconBtn: (danger) => ({
    padding:'6px 10px', borderRadius:5, border:'1px solid var(--border)',
    background:'none', color: danger ? 'var(--red)' : 'var(--muted)', cursor:'pointer', fontSize:13,
  }),
  addBtn: {
    padding:'7px 14px', borderRadius:6, fontSize:12, fontWeight:500,
    border:'1px dashed var(--border)', background:'none', color:'var(--muted)',
    cursor:'pointer', marginTop:4,
  },

  tcRow: { display:'grid', gridTemplateColumns:'1fr 2fr auto', gap:10, alignItems:'start', marginBottom:8 },

  runBar: { display:'flex', gap:12, alignItems:'center', marginTop:24 },
  runBtn: (disabled) => ({
    padding:'10px 24px', borderRadius:6, fontSize:14, fontWeight:600,
    border:'none', cursor: disabled ? 'not-allowed' : 'pointer',
    background: disabled ? 'var(--border)' : 'var(--accent)',
    color: disabled ? 'var(--muted)' : 'var(--bg)',
    opacity: disabled ? 0.6 : 1,
  }),

  progress: {
    marginTop:16, padding:14, borderRadius:6, background:'rgba(123,164,247,0.06)',
    border:'1px solid rgba(123,164,247,0.2)', fontSize:13, color:'var(--accent)',
  },
  errBox: {
    marginTop:12, padding:12, borderRadius:6, background:'rgba(248,113,113,0.07)',
    border:'1px solid rgba(248,113,113,0.25)', fontSize:12, color:'var(--red)',
    whiteSpace:'pre-wrap', fontFamily:'monospace',
  },

  code: {
    background:'var(--bg)', border:'1px solid var(--border)', borderRadius:8,
    padding:20, fontSize:12, color:'var(--text)', fontFamily:'monospace',
    whiteSpace:'pre', overflowX:'auto', lineHeight:1.6, marginBottom:16,
  },
  copyBtn: {
    ...btnSecondary, fontSize:12, padding:'6px 14px',
  },
  devSection: { marginBottom:28 },
  devH: { fontSize:13, fontWeight:600, color:'var(--text)', margin:'0 0 10px 0' },
  devSub: { fontSize:12, color:'var(--muted)', margin:'0 0 12px 0', lineHeight:1.5 },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const mkStep = () => ({ name: '', system_prompt: '', user_prompt_template: '{{input}}' })
const mkBranch = (label) => ({
  name: label, model_id: 'gpt-4o-mini', temperature: 0.7,
  steps: [mkStep()], provider_id: null,
})
const mkTestCase = () => ({ label: '', input: '' })

function uid() { return Math.random().toString(36).slice(2, 8) }

// ── Sub-components ────────────────────────────────────────────────────────────

function Input({ label, value, onChange, placeholder, hint, type = 'text', id }) {
  const [focused, setFocused] = useState(false)
  const inputId = id || (label ? `wb-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)
  return (
    <div style={S.row}>
      {label && <label htmlFor={inputId} style={S.label}>{label}</label>}
      <input
        id={inputId}
        type={type}
        style={{ ...S.input, borderColor: focused ? 'var(--accent)' : 'var(--border)' }}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder || ''}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
      {hint && <p style={S.hint}>{hint}</p>}
    </div>
  )
}

function Textarea({ label, value, onChange, placeholder, rows = 3, hint, id }) {
  const [focused, setFocused] = useState(false)
  const inputId = id || (label ? `wb-${label.toLowerCase().replace(/\s+/g, '-')}` : undefined)
  return (
    <div style={S.row}>
      {label && <label htmlFor={inputId} style={S.label}>{label}</label>}
      <textarea
        id={inputId}
        style={{ ...S.textarea, borderColor: focused ? 'var(--accent)' : 'var(--border)', minHeight: rows * 22 }}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder || ''}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
      {hint && <p style={S.hint}>{hint}</p>}
    </div>
  )
}

function StepEditor({ step, idx, onChange, onRemove, canRemove }) {
  return (
    <div style={S.stepRow}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <span style={S.stepNum}>Step {idx + 1}</span>
        {canRemove && (
          <button style={S.iconBtn(true)} onClick={onRemove} title="Remove step" aria-label={`Remove step ${idx + 1}`}>✕</button>
        )}
      </div>
      <Input
        label="Step Name"
        value={step.name}
        onChange={v => onChange({ ...step, name: v })}
        placeholder="e.g. Classify, Summarize, Generate"
      />
      <Textarea
        label={<>System Prompt<InfoTip text="Instructions that set the AI's behavior and persona. For example: 'You are a legal assistant that summarizes contracts.' This stays the same for every test case." /></>}
        value={step.system_prompt}
        onChange={v => onChange({ ...step, system_prompt: v })}
        placeholder="You are a helpful assistant…"
        rows={2}
      />
      <Textarea
        label={<>User Prompt Template<InfoTip text="The actual question or request sent to the model. Use {{input}} as a placeholder — it gets replaced with each test case. For example: 'Summarize this: {{input}}'" /></>}
        value={step.user_prompt_template}
        onChange={v => onChange({ ...step, user_prompt_template: v })}
        placeholder="{{input}}"
        hint="Use {{input}} where the test case input should be inserted."
        rows={2}
      />
    </div>
  )
}

function BranchEditor({ branch, label, colorHex, side, onChange, tip, providers }) {
  function updateStep(idx, step) {
    const steps = [...branch.steps]
    steps[idx] = step
    onChange({ ...branch, steps })
  }
  function addStep() { onChange({ ...branch, steps: [...branch.steps, mkStep()] }) }
  function removeStep(idx) {
    onChange({ ...branch, steps: branch.steps.filter((_, i) => i !== idx) })
  }

  const showProviderPicker = providers && providers.length > 1

  return (
    <div style={S.card(side || 'A')}>
      <h3 style={{ ...S.cardH }}>
        <span style={{ width:10, height:10, borderRadius:'50%', background:colorHex, display:'inline-block' }} />
        {label}
        {tip && <InfoTip text={tip} />}
      </h3>
      <div style={S.twoCol}>
        <Input
          label="Branch Name"
          value={branch.name}
          onChange={v => onChange({ ...branch, name: v })}
          placeholder="e.g. Production v1"
        />
        <Input
          label="Model ID"
          value={branch.model_id}
          onChange={v => onChange({ ...branch, model_id: v })}
          placeholder="gpt-4o-mini"
          hint="Any OpenAI or OpenRouter model ID"
        />
      </div>
      {showProviderPicker && (
        <div style={S.row}>
          <label style={S.label}>
            Provider
            <InfoTip text="Each branch can use a different LLM provider — useful for comparing OpenAI vs. Anthropic on the same prompts." />
          </label>
          <select
            style={S.input}
            value={branch.provider_id || ''}
            onChange={e => onChange({ ...branch, provider_id: e.target.value || null })}
          >
            <option value="">Default Provider{providers.find(p => p.is_default) ? ` (${providers.find(p => p.is_default).name})` : ''}</option>
            {providers.filter(p => !p.is_default).map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}
      <div style={S.row}>
        <label htmlFor={`wb-temp-${label}`} style={S.label}>Temperature <span style={{ color:'var(--accent)' }}>{branch.temperature}</span><InfoTip text="Controls how random the model's output is. Lower values (0.0–0.3) give consistent, predictable answers. Higher values (0.7–1.5) give more creative, varied responses. 0.7 is a good default." /></label>
        <input
          id={`wb-temp-${label}`}
          type="range" min={0} max={2} step={0.1}
          value={branch.temperature}
          onChange={e => onChange({ ...branch, temperature: parseFloat(e.target.value) })}
          style={{ width:'100%' }}
        />
      </div>
      <label style={{ ...S.label, marginBottom:8 }}>Steps</label>
      {branch.steps.map((step, idx) => (
        <StepEditor
          key={idx}
          step={step}
          idx={idx}
          onChange={s => updateStep(idx, s)}
          onRemove={() => removeStep(idx)}
          canRemove={branch.steps.length > 1}
        />
      ))}
      <button style={S.addBtn} onClick={addStep}>+ Add Step</button>
    </div>
  )
}

// ── No-code Mode ──────────────────────────────────────────────────────────────

function NoCodeMode({ nav }) {
  const [wfName,     setWfName]     = useState('')
  const [evalName,   setEvalName]   = useState('')
  const [branchA,    setBranchA]    = useState(() => mkBranch('Branch A'))
  const [branchB,    setBranchB]    = useState(() => mkBranch('Branch B'))
  const [testCases,  setTestCases]  = useState([{ ...mkTestCase(), _id: uid() }])
  const [tsMode,     setTsMode]     = useState('manual')  // 'manual' | 'testset'
  const [testSets,   setTestSets]   = useState([])
  const [selTsId,    setSelTsId]    = useState('')
  const [tsCases,    setTsCases]    = useState([])
  const [running,    setRunning]    = useState(false)
  const [runErrors,  setRunErrors]  = useState([])
  const [providers,  setProviders]  = useState([])

  // Load providers on mount
  useState(() => {
    api.listProviders().then(ps => setProviders(ps || [])).catch(() => {})
  })

  // Load test sets when user switches to testset mode
  async function loadTestSets() {
    try {
      const data = await api.listTestSets()
      setTestSets(data || [])
    } catch { /* ignore */ }
  }

  async function selectTestSet(tsId) {
    setSelTsId(tsId)
    if (!tsId) { setTsCases([]); return }
    try {
      const data = await api.getTestSet(tsId)
      setTsCases(data.cases || [])
    } catch { /* ignore */ }
  }

  function addTestCase() { setTestCases(tc => [...tc, { ...mkTestCase(), _id: uid() }]) }
  function removeTestCase(id) { setTestCases(tc => tc.filter(c => c._id !== id)) }
  function updateTestCase(id, field, val) {
    setTestCases(tc => tc.map(c => c._id === id ? { ...c, [field]: val } : c))
  }

  const effectiveCases = tsMode === 'testset' ? tsCases : testCases

  function validate() {
    if (!wfName.trim())    return 'Workflow name is required'
    if (!evalName.trim())  return 'Eval run name is required'
    if (!branchA.name.trim() || !branchB.name.trim()) return 'Both branch names are required'
    if (!branchA.model_id.trim() || !branchB.model_id.trim()) return 'Both model IDs are required'
    if (effectiveCases.length === 0) return 'Add at least one test case'
    for (const tc of effectiveCases) {
      if (!tc.label?.trim()) return 'All test cases need a label'
      if (!tc.input?.trim()) return 'All test cases need an input'
    }
    return null
  }

  async function run() {
    const err = validate()
    if (err) { dispatchApiError(err); return }

    setRunning(true)
    setRunErrors([])

    const body = {
      workflow_name: wfName.trim(),
      eval_run_name: evalName.trim(),
      branch_a: {
        name: branchA.name,
        model_id: branchA.model_id,
        temperature: branchA.temperature,
        ...(branchA.provider_id ? { provider_id: branchA.provider_id } : {}),
        steps: branchA.steps.map(s => ({
          name: s.name || `step_${branchA.steps.indexOf(s) + 1}`,
          system_prompt: s.system_prompt,
          user_prompt_template: s.user_prompt_template || '{{input}}',
        })),
      },
      branch_b: {
        name: branchB.name,
        model_id: branchB.model_id,
        temperature: branchB.temperature,
        ...(branchB.provider_id ? { provider_id: branchB.provider_id } : {}),
        steps: branchB.steps.map(s => ({
          name: s.name || `step_${branchB.steps.indexOf(s) + 1}`,
          system_prompt: s.system_prompt,
          user_prompt_template: s.user_prompt_template || '{{input}}',
        })),
      },
      test_cases: effectiveCases.map(tc => ({
        label: tc.label,
        input: tc.input,
      })),
    }

    try {
      const result = await api.runWorkflow(body)
      if (result.errors?.length) setRunErrors(result.errors)
      window.dispatchEvent(new CustomEvent('fp:apisuccess', {
        detail: { message: `Eval run created with ${effectiveCases.length} test cases` }
      }))
      if (result.eval_run_id) {
        setTimeout(() => nav('evalRunDetail', { evalRunId: result.eval_run_id }), 600)
      }
    } catch (e) {
      dispatchApiError(e.message || 'Runner failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      {/* Workflow meta */}
      <div style={S.card()}>
        <h3 style={S.cardH}>Workflow Info</h3>
        <div style={S.twoCol}>
          <Input label="Workflow Name" value={wfName} onChange={setWfName}
            placeholder="e.g. Customer Support Triage"
            hint="Reuses an existing workflow if the name matches, or creates a new one."
          />
          <Input label="Eval Run Name" value={evalName} onChange={setEvalName}
            placeholder="e.g. GPT-4o vs GPT-4o-mini — May 2026"
          />
        </div>
      </div>

      {/* Branch configs */}
      <BranchEditor branch={branchA} label="Branch A (Baseline)" colorHex="var(--accent)" side="A" onChange={setBranchA}
        tip="Your current setup — the model or prompt you're comparing against. Think of this as the 'control' in an experiment."
        providers={providers} />
      <BranchEditor branch={branchB} label="Branch B (Challenger)" colorHex="var(--green)" side="B" onChange={setBranchB}
        tip="The new thing you're testing — a different model, prompt, or temperature. This is what you want to evaluate."
        providers={providers} />

      {/* Test cases */}
      <div style={S.card()}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
          <h3 style={{ ...S.cardH, margin:0 }}>
            Test Cases
            <span style={S.badge}>{effectiveCases.length}</span>
          </h3>
          <div style={{ display:'flex', gap:6 }}>
            <button
              style={{ ...S.tab(tsMode === 'manual'), borderRadius:5, border:`1px solid ${'var(--border)'}`, padding:'5px 12px' }}
              onClick={() => setTsMode('manual')}
            >Manual</button>
            <button
              style={{ ...S.tab(tsMode === 'testset'), borderRadius:5, border:`1px solid ${'var(--border)'}`, padding:'5px 12px' }}
              onClick={() => { setTsMode('testset'); loadTestSets() }}
            >From Test Set</button>
          </div>
        </div>

        {tsMode === 'testset' ? (
          <div>
            <div style={S.row}>
              <label htmlFor="wb-test-set" style={S.label}>Select Test Set</label>
              <select
                id="wb-test-set"
                style={S.input}
                value={selTsId}
                onChange={e => selectTestSet(e.target.value)}
              >
                <option value="">— choose a test set —</option>
                {testSets.map(ts => (
                  <option key={ts.id} value={ts.id}>{ts.name} ({ts.cases?.length ?? 0} cases)</option>
                ))}
              </select>
              <p style={S.hint}>
                Test Sets are managed in <strong>Test Sets</strong> in the sidebar.
                You can import CSVs there and reuse them across eval runs.
              </p>
            </div>
            {tsCases.length > 0 && (
              <div style={{ fontSize:12, color:'var(--muted)' }}>
                {tsCases.slice(0, 4).map((tc, i) => (
                  <div key={i} style={{ padding:'4px 0', borderBottom:`1px solid ${'var(--border)'}` }}>
                    <strong>{tc.label}</strong> — {(tc.input || '').slice(0, 80)}{(tc.input || '').length > 80 ? '…' : ''}
                  </div>
                ))}
                {tsCases.length > 4 && <div style={{ paddingTop:4 }}>…and {tsCases.length - 4} more</div>}
              </div>
            )}
          </div>
        ) : (
          <div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 2fr auto', gap:8, marginBottom:6 }}>
              <span style={S.label}>Label</span>
              <span style={S.label}>Input</span>
              <span />
            </div>
            {testCases.map(tc => (
              <div key={tc._id} style={S.tcRow}>
                <input
                  style={S.input}
                  placeholder="test-case-1"
                  value={tc.label}
                  onChange={e => updateTestCase(tc._id, 'label', e.target.value)}
                />
                <input
                  style={S.input}
                  placeholder="Input text for this case…"
                  value={tc.input}
                  onChange={e => updateTestCase(tc._id, 'input', e.target.value)}
                />
                <button
                  style={S.iconBtn(true)}
                  onClick={() => removeTestCase(tc._id)}
                  disabled={testCases.length === 1}
                  aria-label={`Remove test case ${tc.label || ''}`}
                >✕</button>
              </div>
            ))}
            <button style={S.addBtn} onClick={addTestCase}>+ Add Test Case</button>
            <p style={{ ...S.hint, marginTop:8 }}>
              Tip: for larger test suites, create a <strong>Test Set</strong> in the sidebar and use "From Test Set" above.
            </p>
          </div>
        )}
      </div>

      {/* Run */}
      <div style={S.runBar}>
        <button style={S.runBtn(running)} disabled={running} onClick={run}>
          {running ? '⏳ Running…' : '▶  Run Eval'}
        </button>
        {running && (
          <div style={S.progress}>
            Calling {effectiveCases.length} test case{effectiveCases.length !== 1 ? 's' : ''} on both branches…
            this may take a minute. You'll be redirected when done.
          </div>
        )}
      </div>
      {runErrors.length > 0 && (
        <div style={S.errBox}>
          {runErrors.length} step error{runErrors.length !== 1 ? 's' : ''}:{'\n'}
          {runErrors.join('\n')}
        </div>
      )}
    </div>
  )
}

// ── Developer Mode ────────────────────────────────────────────────────────────

const SNIPPET = `"""
Forkmark — Python SDK snippet
Generated by the Workflow Builder

Prerequisites:
    pip install requests
    forkmark running at http://localhost:7700
    FM_KEY set to a valid Forkmark API key (create one in API Keys)
"""
import os, requests, uuid

BASE  = "http://localhost:7700/api"
KEY   = os.environ["FM_KEY"]          # create in Forkmark → API Keys
HEADS = {"X-API-Key": KEY, "Content-Type": "application/json"}

def api(method, path, data=None):
    r = getattr(requests, method)(BASE + path, json=data, headers=HEADS, timeout=60)
    r.raise_for_status()
    return r.json()

# ── 1. Create / reuse a workflow ──────────────────────────────────────────────
wf = api("post", "/workflows", {"name": "My Workflow"})

# ── 2. Create an eval run ─────────────────────────────────────────────────────
er = api("post", "/eval-runs", {
    "workflow_name":  wf["name"],
    "name":           "gpt-4o-mini vs gpt-3.5-turbo — May 2026",
    "description":    "Challenger vs Production",
    "branch_a_config": {"name": "Challenger", "model_id": "gpt-4o-mini"},
    "branch_b_config": {"name": "Production",  "model_id": "gpt-3.5-turbo"},
})
er_id = er["id"]

TEST_CASES = [
    {"label": "case-1", "input": "What is the return policy?"},
    {"label": "case-2", "input": "My order hasn't arrived."},
    # … add more
]

for tc in TEST_CASES:
    # Create a run
    run = api("post", "/sdk/runs", {
        "workflow_id":    wf["id"],
        "eval_run_id":    er_id,
        "test_case_label": tc["label"],
        "input_data":     {"input": tc["input"]},
    })
    run_id = run["id"]

    # Two branches — run your model calls here
    for branch_name, model_id in [("Challenger", "gpt-4o-mini"), ("Production", "gpt-3.5-turbo")]:
        branch = api("post", "/sdk/branches", {
            "run_id":      run_id,
            "workflow_id": wf["id"],
            "name":        branch_name,
            "model_id":    model_id,
            "temperature": 0.7,
        })
        # --- call your model here ---
        output_text  = f"[model output for {branch_name}]"  # replace with real call
        tokens_input = 50
        tokens_output = 80
        latency_ms   = 320
        # ----------------------------
        api("post", "/sdk/steps", {
            "run_id":         run_id,
            "branch_id":      branch["id"],
            "step_name":      "respond",
            "step_index":     0,
            "input_messages": [{"role":"user","content": tc["input"]}],
            "output_text":    output_text,
            "model_id":       model_id,
            "temperature":    0.7,
            "tokens_input":   tokens_input,
            "tokens_output":  tokens_output,
            "latency_ms":     latency_ms,
        })

    # Create comparison + complete run
    api("post", "/sdk/comparisons", {
        "run_id":       run_id,
        "workflow_id":  wf["id"],
        "branch_a_id":  run["branch_a_id"],   # adjust if your SDK returns IDs differently
        "branch_b_id":  run["branch_b_id"],
        "step_names":   ["respond"],
        "eval_run_id":  er_id,
        "test_case_label": tc["label"],
    })
    api("patch", f"/sdk/runs/{run_id}/complete", {"status": "completed"})

# Complete the eval run
api("patch", f"/sdk/eval-runs/{er_id}/complete", {"status": "completed"})

print(f"Done — open http://localhost:7700/#evalRunDetail?evalRunId={er_id}")
`

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <button style={S.copyBtn} onClick={copy}>
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

function DevMode() {
  return (
    <div>
      <div style={S.card()}>
        <h3 style={S.cardH}>How it works</h3>
        <p style={{ fontSize:13, color:'var(--muted)', lineHeight:1.7, margin:0 }}>
          The Forkmark SDK lets you drive comparisons from any Python script.
          Your production code calls the Forkmark API directly after each model invocation —
          no wrappers, no monkey-patching. You own the model calls.
        </p>
      </div>

      <div style={S.devSection}>
        <h3 style={S.devH}>Step 1 — Create an API key</h3>
        <p style={S.devSub}>Go to <strong>API Keys</strong> in the sidebar and create a key. Set it as <code>FM_KEY</code> in your environment.</p>
      </div>

      <div style={S.devSection}>
        <h3 style={S.devH}>Step 2 — Install the requests library</h3>
        <pre style={{ ...S.code, padding:'12px 16px', marginBottom:8 }}>pip install requests</pre>
      </div>

      <div style={S.devSection}>
        <h3 style={S.devH}>Step 3 — Copy and adapt this snippet</h3>
        <p style={S.devSub}>
          Replace the placeholder model calls with your real OpenAI / Anthropic / Bedrock calls.
          The snippet handles workflow creation, eval run tracking, branch logging, and completion.
        </p>
        <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:8 }}>
          <CopyButton text={SNIPPET} />
        </div>
        <pre style={S.code}>{SNIPPET}</pre>
      </div>

      <div style={S.devSection}>
        <h3 style={S.devH}>Step 4 — Where to store test cases</h3>
        <p style={S.devSub}>
          Option A — <strong>Inline</strong>: define a <code>TEST_CASES</code> list in your script (shown above).<br />
          Option B — <strong>Test Sets</strong>: create a Test Set in the sidebar, import a CSV, then load via the API:
        </p>
        <pre style={{ ...S.code, padding:'12px 16px' }}>
{`# Load cases from a saved Test Set
ts = api("get", "/test-sets/<test-set-id>")
TEST_CASES = [{"label": c["label"], "input": c["input"]} for c in ts["cases"]]`}
        </pre>
      </div>

      <div style={S.devSection}>
        <h3 style={S.devH}>Key parameters you can vary</h3>
        <div style={{ ...S.card(), background:'var(--bg)' }}>
          {[
            ['model_id',     'Any OpenAI-compatible model ID (gpt-4o, claude-3-5-sonnet, etc.)'],
            ['temperature',  '0.0–2.0 — controls output randomness'],
            ['step_name',    'Logical name for the pipeline step (classify, summarize, etc.)'],
            ['step_index',   'Zero-based ordering within a run — enables multi-step divergence'],
            ['input_messages','Full message history sent to the model (system + user + prior turns)'],
            ['test_case_label','Human-readable label shown in the reviewer UI'],
          ].map(([k, v]) => (
            <div key={k} style={{ display:'flex', gap:12, padding:'8px 0', borderBottom:`1px solid ${'var(--border)'}`, fontSize:13 }}>
              <code style={{ color:'var(--accent)', minWidth:140, flexShrink:0 }}>{k}</code>
              <span style={{ color:'var(--muted)' }}>{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function WorkflowBuilder({ nav }) {
  const [mode, setMode] = useState('nocode')  // 'nocode' | 'dev'

  return (
    <div style={pageStyle(900)}>
      <PageHeader title="Workflow Runner" subtitle="Run A/B comparisons between two model configurations. Choose No-code mode to run directly from the browser, or Developer mode for a Python SDK snippet." />

      <div style={S.tabs} role="tablist" aria-label="Workflow runner mode">
        <button style={S.tab(mode === 'nocode')} onClick={() => setMode('nocode')} role="tab" aria-selected={mode === 'nocode'}>
          🖱  No-code Mode
        </button>
        <button style={S.tab(mode === 'dev')} onClick={() => setMode('dev')} role="tab" aria-selected={mode === 'dev'}>
          {'</>'}  Developer Mode
        </button>
      </div>

      <div role="tabpanel" aria-label={mode === 'nocode' ? 'No-code Mode' : 'Developer Mode'}>
        {mode === 'nocode' && <NoCodeMode nav={nav} />}
        {mode === 'dev'    && <DevMode />}
      </div>
    </div>
  )
}
