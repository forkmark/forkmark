import { emptyState as S, btnPrimary } from './styles.js'

/**
 * Shared empty state with optional icon, heading, body text, and CTA.
 *
 * Props:
 *   icon     - optional emoji/icon string
 *   heading  - main heading text
 *   body     - descriptive text
 *   action   - optional { label, onClick } for a CTA button
 */
export default function EmptyState({ icon, heading, body, action }) {
  return (
    <div style={S.wrap}>
      {icon && <div style={{ fontSize: 32, marginBottom: 12 }}>{icon}</div>}
      {heading && <div style={S.heading}>{heading}</div>}
      {body && <div style={S.body}>{body}</div>}
      {action && (
        <button style={{ ...btnPrimary, marginTop: 16 }} onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}
