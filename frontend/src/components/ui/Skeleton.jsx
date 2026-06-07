/**
 * Skeleton loading placeholders.
 * Provides a pulsing animation placeholder for content that's loading.
 */

const pulse = {
  background: 'linear-gradient(90deg, var(--surface2) 25%, var(--border) 50%, var(--surface2) 75%)',
  backgroundSize: '200% 100%',
  animation: 'skeleton-pulse 1.5s ease-in-out infinite',
  borderRadius: 4,
}

// Inject keyframes once
if (typeof document !== 'undefined' && !document.getElementById('skeleton-keyframes')) {
  const style = document.createElement('style')
  style.id = 'skeleton-keyframes'
  style.textContent = `@keyframes skeleton-pulse { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }`
  document.head.appendChild(style)
}

export function SkeletonLine({ width = '100%', height = 14, style: extra }) {
  return <div style={{ ...pulse, width, height, ...extra }} />
}

export function SkeletonCard({ height = 80, style: extra }) {
  return <div style={{ ...pulse, height, borderRadius: 8, ...extra }} />
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* Header */}
      <div style={{ display: 'flex', gap: 12 }}>
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonLine key={i} width={`${100 / cols}%`} height={12} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: 12, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
          {Array.from({ length: cols }).map((_, j) => (
            <SkeletonLine key={j} width={`${100 / cols}%`} height={16} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonStatCards({ count = 4 }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${count}, 1fr)`, gap: 12 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '16px 20px' }}>
          <SkeletonLine width="60%" height={10} style={{ marginBottom: 10 }} />
          <SkeletonLine width="40%" height={28} />
        </div>
      ))}
    </div>
  )
}
