import { useState } from 'react'
import { divColor } from './constants.js'

/**
 * DivergenceDotPlot — horizontal strip chart showing divergence distribution.
 *
 * Each comparison is a dot positioned by its divergence score (0-1),
 * colored green/orange/red by severity. Provides an at-a-glance
 * distribution overview that no standard bar chart can match.
 *
 * Props:
 *   comparisons - array of { id, divergence_score, test_case_label? }
 *   onDotClick  - optional (comp) => void
 *   height      - strip height in px (default 48)
 */

const S = {
  wrap: {
    padding: '16px 0',
  },
  label: {
    fontSize: 10, fontWeight: 500, textTransform: 'uppercase',
    letterSpacing: '0.08em', color: 'var(--muted)', marginBottom: 10,
  },
  strip: (h) => ({
    position: 'relative', height: h, width: '100%',
    background: 'var(--surface)',
    borderRadius: 6,
    border: '1px solid var(--border)',
    overflow: 'visible',
  }),
  axis: {
    display: 'flex', justifyContent: 'space-between',
    fontSize: 9, color: 'var(--muted)', marginTop: 6, fontWeight: 500,
    letterSpacing: '0.04em',
  },
  dot: (x, color, size, interactive) => ({
    position: 'absolute',
    left: `${x}%`,
    top: '50%',
    transform: 'translate(-50%, -50%)',
    width: size, height: size,
    borderRadius: '50%',
    background: color,
    opacity: 0.85,
    cursor: interactive ? 'pointer' : 'default',
    transition: 'transform 0.15s, opacity 0.15s',
    zIndex: 1,
  }),
  tooltip: {
    position: 'absolute',
    top: -32,
    left: '50%',
    transform: 'translateX(-50%)',
    background: 'var(--surface2)',
    border: '1px solid var(--border)',
    padding: '3px 8px',
    borderRadius: 4,
    fontSize: 10,
    color: 'var(--text)',
    whiteSpace: 'nowrap',
    pointerEvents: 'none',
    zIndex: 10,
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
  },
  median: (x) => ({
    position: 'absolute',
    left: `${x}%`,
    top: 0,
    bottom: 0,
    width: 1,
    background: 'var(--muted)',
    opacity: 0.4,
    zIndex: 0,
  }),
}

export default function DivergenceDotPlot({ comparisons = [], onDotClick, height = 48 }) {
  const [hoveredId, setHoveredId] = useState(null)

  if (comparisons.length === 0) return null

  // Calculate median
  const scores = comparisons
    .map(c => c.divergence_score)
    .filter(s => s != null)
    .sort((a, b) => a - b)

  const median = scores.length > 0
    ? scores[Math.floor(scores.length / 2)]
    : null

  // Jitter dots vertically to reduce overlap
  const jitter = (idx, total) => {
    if (total <= 1) return 0
    const band = 0.6 // use 60% of height for jittering
    const step = band / Math.min(total, 8)
    return ((idx % 8) - 3.5) * step * height
  }

  return (
    <div style={S.wrap}>
      <div style={S.label}>Divergence Distribution</div>
      <div style={S.strip(height)}>
        {/* Median line */}
        {median != null && <div style={S.median(median * 100)} />}

        {/* Zone indicators */}
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '20%', background: 'rgba(74,222,128,0.04)', borderRadius: '6px 0 0 6px' }} />
        <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: '40%', background: 'rgba(248,113,113,0.04)', borderRadius: '0 6px 6px 0' }} />

        {/* Dots */}
        {comparisons.map((c, idx) => {
          const score = c.divergence_score
          if (score == null) return null
          const x = Math.max(2, Math.min(98, score * 100))
          const color = divColor(score)
          const size = hoveredId === c.id ? 10 : 7
          const isHovered = hoveredId === c.id

          return (
            <div
              key={c.id}
              style={{
                ...S.dot(x, color, size, !!onDotClick),
                ...(isHovered ? { opacity: 1, transform: 'translate(-50%, -50%) scale(1.4)', zIndex: 5 } : {}),
              }}
              onMouseEnter={() => setHoveredId(c.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onDotClick?.(c)}
            >
              {isHovered && (
                <div style={S.tooltip}>
                  <span style={{ fontWeight: 600 }}>{(score * 100).toFixed(0)}%</span>
                  {c.test_case_label && <span style={{ color: 'var(--muted)', marginLeft: 4 }}>{c.test_case_label}</span>}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div style={S.axis}>
        <span style={{ color: 'var(--green)' }}>0% identical</span>
        <span>50%</span>
        <span style={{ color: 'var(--red)' }}>100% divergent</span>
      </div>
    </div>
  )
}

