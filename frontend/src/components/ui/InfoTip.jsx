import { useState } from 'react'

const S = {
  wrap: {
    display: 'inline-flex', alignItems: 'center', position: 'relative',
    marginLeft: 6, verticalAlign: 'middle',
  },
  icon: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 16, height: 16, borderRadius: '50%',
    background: 'rgba(123,164,247,0.12)', color: 'var(--accent)',
    fontSize: 10, fontWeight: 700, cursor: 'help',
    border: '1px solid rgba(123,164,247,0.25)',
    fontFamily: 'var(--font)',
    lineHeight: 1, userSelect: 'none',
  },
  tip: {
    position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)',
    marginBottom: 8,
    background: 'var(--surface2)', border: '1px solid var(--border)',
    borderRadius: 8, padding: '10px 14px',
    fontSize: 12, color: 'var(--text)', lineHeight: 1.5,
    fontWeight: 400, whiteSpace: 'normal',
    minWidth: 220, maxWidth: 300,
    boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
    zIndex: 100, pointerEvents: 'none',
    textTransform: 'none', letterSpacing: 'normal',
  },
  arrow: {
    position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)',
    width: 0, height: 0,
    borderLeft: '6px solid transparent',
    borderRight: '6px solid transparent',
    borderTop: '6px solid var(--border)',
  },
}

/**
 * A small (i) icon that shows a tooltip on hover.
 * Usage: <InfoTip text="Temperature controls randomness..." />
 */
export default function InfoTip({ text }) {
  const [show, setShow] = useState(false)

  return (
    <span
      style={S.wrap}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onClick={() => setShow(v => !v)}
    >
      <span style={S.icon} aria-label="More information" role="button" tabIndex={0}>i</span>
      {show && (
        <div style={S.tip} role="tooltip">
          {text}
          <span style={S.arrow} />
        </div>
      )}
    </span>
  )
}
