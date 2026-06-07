// ── Shared style primitives ─────────────────────────────────────────────────
// Common inline style objects reused across many components.
// Import what you need: import { pageStyle, tableStyles, ... } from './ui/styles.js'

// ── Page layouts ───────────────────────────────────────────────────────────
export const pageStyle = (maxWidth = 1100) => ({
  padding: '24px',
  maxWidth,
})

export const pageHeader = {
  h1:   { fontSize: 24, fontWeight: 800, marginBottom: 4, letterSpacing: '-0.03em' },
  muted:{ color: 'var(--muted)', fontSize: 13, marginBottom: 24, fontWeight: 400 },
}

export const toolbar = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16,
}

// ── Panel / Card ───────────────────────────────────────────────────────────
export const panel = {
  background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8,
  boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08)',
}

/** Panel with a colored left accent bar — the Forkmark visual signature. */
export const accentPanel = (color = 'var(--accent)') => ({
  ...panel,
  borderLeft: `3px solid ${color}`,
  borderRadius: '2px 8px 8px 2px',
})

export const panelHeader = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  padding: '14px 16px', borderBottom: '1px solid var(--border)',
  fontSize: 13, fontWeight: 600, letterSpacing: '-0.01em',
}

export const statCard = {
  card:  { padding: '16px 4px' },
  label: { fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, fontWeight: 500 },
  value: (color) => ({ fontSize: 32, fontWeight: 800, color: color || 'var(--text)', letterSpacing: '-0.04em', lineHeight: 1.1 }),
}

// ── Table ──────────────────────────────────────────────────────────────────
export const tableStyles = {
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th:    { padding: '8px 14px', textAlign: 'left', color: 'var(--muted)', fontWeight: 500, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)' },
  td:    { padding: '10px 14px', borderTop: '1px solid var(--border)', verticalAlign: 'middle' },
  row:   { cursor: 'pointer', transition: 'background 0.1s' },
}

// ── Buttons ────────────────────────────────────────────────────────────────
export const btnPrimary = {
  fontSize: 13, padding: '8px 16px',
  background: 'var(--accent)', color: 'var(--bg)',
  border: 'none', borderRadius: 6, fontWeight: 700, cursor: 'pointer',
  letterSpacing: '-0.01em',
}

export const btnSecondary = {
  fontSize: 12, padding: '6px 14px',
  background: 'transparent', color: 'var(--muted)',
  border: '1px solid var(--border)', borderRadius: 5, cursor: 'pointer',
  letterSpacing: '-0.01em',
}

export const btnDanger = {
  fontSize: 11, padding: '4px 10px',
  background: 'transparent', color: 'var(--red)',
  border: '1px solid var(--red)', borderRadius: 4, cursor: 'pointer',
}

// ── Modal / Overlay ────────────────────────────────────────────────────────
export const modalStyles = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  },
  box: (width = 440) => ({
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, padding: 24, width, maxHeight: '90vh', overflowY: 'auto',
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
  }),
  title:    { fontSize: 16, fontWeight: 800, marginBottom: 4, letterSpacing: '-0.02em' },
  subtitle: { color: 'var(--muted)', fontSize: 12, marginBottom: 20 },
  footer:   { display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 },
}

// ── Form ───────────────────────────────────────────────────────────────────
export const formStyles = {
  label: { fontSize: 11, color: 'var(--muted)', marginBottom: 4, display: 'block', fontWeight: 500, letterSpacing: '0.01em' },
  input: {
    width: '100%', background: 'var(--surface2)', border: '1px solid var(--border)',
    borderRadius: 5, color: 'var(--text)', padding: '8px 10px', fontSize: 13,
    boxSizing: 'border-box', marginBottom: 10, fontFamily: 'var(--font)',
  },
  select: {
    background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 5,
    color: 'var(--text)', padding: '7px 10px', fontSize: 12, fontFamily: 'var(--font)',
    width: '100%', boxSizing: 'border-box',
  },
  row2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 },
}

// ── Empty state ────────────────────────────────────────────────────────────
export const emptyState = {
  wrap:    { padding: '48px 24px', color: 'var(--muted)', textAlign: 'center' },
  heading: { fontSize: 16, fontWeight: 700, marginBottom: 8, color: 'var(--text)', letterSpacing: '-0.02em' },
  body:    { fontSize: 13, lineHeight: 1.6, maxWidth: 420, margin: '0 auto' },
}

// ── Badge / Chip ───────────────────────────────────────────────────────────
export function statusBadge(status) {
  const map = {
    pending:    { color: 'var(--muted)',  bg: 'rgba(107,115,148,0.12)' },
    running:    { color: 'var(--accent)', bg: 'rgba(123,164,247,0.12)' },
    completed:  { color: 'var(--green)',  bg: 'rgba(74,222,128,0.12)' },
    failed:     { color: 'var(--red)',    bg: 'rgba(248,113,113,0.12)' },
    in_progress:{ color: 'var(--orange)', bg: 'rgba(251,191,36,0.12)' },
  }
  const { color, bg } = map[status] || map.pending
  return { color, background: bg, fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600 }
}

export function divBadgeStyle(score) {
  if (score == null) return {}
  const color = score < 0.2 ? 'var(--green)' : score < 0.5 ? 'var(--orange)' : 'var(--red)'
  const bg    = score < 0.2 ? 'rgba(74,222,128,0.12)' : score < 0.5 ? 'rgba(251,191,36,0.12)' : 'rgba(248,113,113,0.12)'
  return { fontWeight: 700, fontSize: 11, color, background: bg, padding: '2px 8px', borderRadius: 8, display: 'inline-block' }
}

// ── Filter chip ────────────────────────────────────────────────────────────
export function filterChip(active) {
  return {
    fontSize: 11, padding: '4px 12px',
    border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
    background: active ? 'rgba(123,164,247,0.1)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--muted)',
    borderRadius: 10, cursor: 'pointer', fontWeight: 600,
  }
}

// ── Branch side colors ─────────────────────────────────────────────────────
export const branchColors = {
  A: { color: 'var(--accent)',  bg: 'rgba(123,164,247,0.1)',  border: '#7ba4f733' },
  B: { color: 'var(--purple)', bg: 'rgba(196,161,245,0.1)', border: '#c4a1f533' },
}

export function branchChip(side) {
  const { color, bg } = branchColors[side] || branchColors.A
  return { color, background: bg, padding: '2px 10px', borderRadius: 5, fontWeight: 600, fontSize: 12 }
}

/** Left accent bar for list rows — color encodes branch or status. */
export function accentRow(color = 'var(--accent)') {
  return {
    borderLeft: `3px solid ${color}`,
    paddingLeft: 12,
  }
}

// ── Interactive row hover helpers ──────────────────────────────────────────
export const hoverHandlers = {
  onMouseEnter: e => e.currentTarget.style.background = 'var(--surface2)',
  onMouseLeave: e => e.currentTarget.style.background = '',
}

export const hoverBorderHandlers = {
  onMouseEnter: e => e.currentTarget.style.borderColor = 'var(--accent)',
  onMouseLeave: e => e.currentTarget.style.borderColor = 'var(--border)',
}
