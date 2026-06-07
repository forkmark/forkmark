import { pageHeader as S, btnPrimary } from './styles.js'

/**
 * Standard page header with title, subtitle, optional back button and action button.
 *
 * Props:
 *   title     - page title
 *   subtitle  - description text
 *   backLabel - optional back link text (e.g. "← Eval Runs")
 *   onBack    - back button click handler
 *   action    - optional { label, onClick } for a primary action button
 *   right     - optional JSX to render on the right side
 */
export default function PageHeader({ title, subtitle, backLabel, onBack, action, right }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {backLabel && onBack && (
            <button
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 13, padding: 0 }}
              onClick={onBack}
            >
              {backLabel}
            </button>
          )}
          <div style={S.h1}>{title}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {right}
          {action && (
            <button style={btnPrimary} onClick={action.onClick}>{action.label}</button>
          )}
        </div>
      </div>
      {subtitle && <div style={S.muted}>{subtitle}</div>}
    </div>
  )
}
