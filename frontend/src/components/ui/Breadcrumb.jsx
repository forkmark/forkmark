/**
 * Breadcrumb — hierarchical navigation trail.
 *
 * Props:
 *   items - array of { label, onClick? } — last item is current (no click)
 *
 * Example:
 *   <Breadcrumb items={[
 *     { label: 'Results', onClick: () => nav('evalRuns') },
 *     { label: 'Run #42' },
 *   ]} />
 */

const S = {
  wrap: {
    display: 'flex', alignItems: 'center', gap: 6,
    fontSize: 12, marginBottom: 6,
  },
  link: {
    color: 'var(--muted)', cursor: 'pointer', fontWeight: 500,
    background: 'none', border: 'none', padding: 0, fontSize: 12,
    fontFamily: 'inherit', letterSpacing: '-0.01em',
    transition: 'color 0.1s',
  },
  sep: {
    color: 'var(--border)', fontSize: 10, userSelect: 'none',
  },
  current: {
    color: 'var(--text)', fontWeight: 600, fontSize: 12,
    letterSpacing: '-0.01em',
  },
}

export default function Breadcrumb({ items = [] }) {
  if (items.length === 0) return null
  return (
    <nav style={S.wrap} aria-label="Breadcrumb">
      {items.map((item, i) => {
        const isLast = i === items.length - 1
        return (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <span style={S.sep} aria-hidden="true">/</span>}
            {isLast ? (
              <span style={S.current} aria-current="page">{item.label}</span>
            ) : (
              <button
                style={S.link}
                onClick={item.onClick}
                onMouseEnter={e => e.target.style.color = 'var(--accent)'}
                onMouseLeave={e => e.target.style.color = 'var(--muted)'}
              >
                {item.label}
              </button>
            )}
          </span>
        )
      })}
    </nav>
  )
}
