import { statCard as S } from './styles.js'

/**
 * Reusable stat card — borderless big-number callout.
 * Used on Dashboard, ReviewQueue, EvalRunDetail, TracingDashboard.
 */
export default function StatCard({ label, value, color }) {
  const accentColor = color || 'var(--accent)'
  return (
    <div style={S.card}>
      <div style={S.value(color)}>{value ?? '—'}</div>
      <div style={{ ...S.label, marginBottom: 0, marginTop: 4, borderBottom: `2px solid ${accentColor}`, paddingBottom: 8, display: 'inline-block' }}>{label}</div>
    </div>
  )
}
