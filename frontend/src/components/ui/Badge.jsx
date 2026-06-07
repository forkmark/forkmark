import { statusBadge, divBadgeStyle } from './styles.js'
import { divColor } from './constants.js'

/**
 * Status badge (pending, running, completed, failed, in_progress)
 */
export function StatusBadge({ status }) {
  return <span style={statusBadge(status)}>{status}</span>
}

/**
 * Divergence score badge with color-coded background.
 * Shows score as percentage.
 */
export function DivBadge({ score }) {
  if (score == null) return <span style={{ color: 'var(--muted)' }}>—</span>
  return (
    <span style={divBadgeStyle(score)}>
      {(score * 100).toFixed(0)}%
    </span>
  )
}

/**
 * Inline divergence text (no background, just colored text).
 */
export function DivText({ score, prefix = 'Δ ' }) {
  if (score == null) return <span style={{ color: 'var(--muted)' }}>—</span>
  return (
    <span style={{ color: divColor(score), fontWeight: 600, fontSize: 12 }}>
      {prefix}{(score * 100).toFixed(0)}%
    </span>
  )
}

/**
 * Generic pill badge
 */
export function Pill({ children, color = 'var(--muted)', bg }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
      color, background: bg || `${color}1a`,
    }}>
      {children}
    </span>
  )
}
