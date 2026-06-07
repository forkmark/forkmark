// ── Shared constants and helpers ────────────────────────────────────────────
// Single source of truth for colors, model pricing, and common formatters.

// ── Model pricing (per 1M tokens: [input, output]) ────────────────────────
export const MODEL_PRICING = {
  'gpt-4o':            [2.50,  10.00],
  'gpt-4o-mini':       [0.15,   0.60],
  'gpt-4-turbo':       [10.00, 30.00],
  'gpt-4':             [30.00, 60.00],
  'gpt-3.5-turbo':     [0.50,   1.50],
  'claude-3-5-sonnet': [3.00,  15.00],
  'claude-3-opus':     [15.00, 75.00],
  'claude-3-haiku':    [0.25,   1.25],
  'mistral-large':     [4.00,  12.00],
  'mistral-medium':    [2.70,   8.10],
}

export const MODELS = Object.keys(MODEL_PRICING)

export function modelCostPer1M(modelId) {
  if (!modelId || typeof modelId !== 'string') return null
  const lower = modelId.toLowerCase()
  for (const [key, prices] of Object.entries(MODEL_PRICING)) {
    if (lower.includes(key)) return prices
  }
  return null
}

export function branchCost(tokens_in, tokens_out, modelId) {
  const p = modelCostPer1M(modelId)
  if (!p) return null
  return ((tokens_in || 0) / 1e6 * p[0]) + ((tokens_out || 0) / 1e6 * p[1])
}

// ── Divergence color helpers ───────────────────────────────────────────────
export function divColor(s) {
  if (s == null) return 'var(--muted)'
  return s < 0.2 ? 'var(--green)' : s < 0.5 ? 'var(--orange)' : 'var(--red)'
}

export function divBg(s) {
  if (s == null) return 'transparent'
  return s < 0.2 ? 'rgba(74,222,128,0.12)' : s < 0.5 ? 'rgba(251,191,36,0.12)' : 'rgba(248,113,113,0.12)'
}

// ── Choice color helpers ───────────────────────────────────────────────────
export const CHOICE_COLORS = { A: '#7ba4f7', B: '#c4a1f5', neither: '#6b7394', both: '#4ade80' }

export function choiceColor(c) { return CHOICE_COLORS[c] || '#6b7394' }

export function choiceBg(c) {
  const hex = CHOICE_COLORS[c]
  if (!hex) return 'rgba(107,115,148,0.12)'
  const r = parseInt(hex.slice(1,3),16)
  const g = parseInt(hex.slice(3,5),16)
  const b = parseInt(hex.slice(5,7),16)
  return `rgba(${r},${g},${b},0.12)`
}

// ── Status color helpers ───────────────────────────────────────────────────
export const STATUS_MAP = {
  pending:   { color: 'var(--muted)',  bg: 'rgba(107,115,148,0.12)' },
  running:   { color: 'var(--accent)', bg: 'rgba(123,164,247,0.12)' },
  completed: { color: 'var(--green)',  bg: 'rgba(74,222,128,0.12)' },
  failed:    { color: 'var(--red)',    bg: 'rgba(248,113,113,0.12)' },
  in_progress:{ color: 'var(--orange)', bg: 'rgba(251,191,36,0.12)' },
}

// ── Date formatting ────────────────────────────────────────────────────────
export function fmtDate(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleDateString(undefined, { month:'short', day:'numeric' })
}

export function fmtDateLong(ts) {
  if (!ts) return 'Never'
  return new Date(ts).toLocaleDateString(undefined, { month:'short', day:'numeric', year:'numeric' })
}

export function fmtDateTime(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString(undefined, { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
}

// ── Number formatting ──────────────────────────────────────────────────────
export function formatNum(n) {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`
  return typeof n === 'number' && !Number.isInteger(n) ? n.toFixed(2) : String(n)
}
