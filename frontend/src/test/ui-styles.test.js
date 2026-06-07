import { describe, it, expect } from 'vitest'
import {
  pageStyle, panel, panelHeader, tableStyles,
  btnPrimary, btnSecondary, btnDanger,
  statusBadge, divBadgeStyle, filterChip,
  branchChip, hoverHandlers,
} from '../components/ui/styles.js'

describe('pageStyle', () => {
  it('returns object with padding and default maxWidth', () => {
    const style = pageStyle()
    expect(style.padding).toBe('24px')
    expect(style.maxWidth).toBe(1100)
  })

  it('accepts custom maxWidth', () => {
    expect(pageStyle(800).maxWidth).toBe(800)
  })
})

describe('panel', () => {
  it('has background, border, and borderRadius', () => {
    expect(panel.background).toBeDefined()
    expect(panel.border).toBeDefined()
    expect(panel.borderRadius).toBe(8)
  })
})

describe('tableStyles', () => {
  it('has table, th, td, row keys', () => {
    expect(tableStyles.table).toBeDefined()
    expect(tableStyles.th).toBeDefined()
    expect(tableStyles.td).toBeDefined()
    expect(tableStyles.row).toBeDefined()
  })

  it('table has full width and collapsed borders', () => {
    expect(tableStyles.table.width).toBe('100%')
    expect(tableStyles.table.borderCollapse).toBe('collapse')
  })
})

describe('button styles', () => {
  it('btnPrimary has accent background', () => {
    expect(btnPrimary.background).toBe('var(--accent)')
    expect(btnPrimary.cursor).toBe('pointer')
  })

  it('btnSecondary has transparent background', () => {
    expect(btnSecondary.background).toBe('transparent')
  })

  it('btnDanger has red color', () => {
    expect(btnDanger.color).toBe('var(--red)')
  })
})

describe('statusBadge', () => {
  it('returns styled object for known statuses', () => {
    const badge = statusBadge('completed')
    expect(badge.color).toBe('var(--green)')
    expect(badge.fontSize).toBe(11)
    expect(badge.borderRadius).toBe(10)
  })

  it('returns pending style for unknown status', () => {
    const badge = statusBadge('unknown')
    expect(badge.color).toBe('var(--muted)')
  })

  it('handles all expected statuses', () => {
    for (const status of ['pending', 'running', 'completed', 'failed', 'in_progress']) {
      const badge = statusBadge(status)
      expect(badge.color).toBeDefined()
      expect(badge.background).toBeDefined()
    }
  })
})

describe('divBadgeStyle', () => {
  it('returns empty object for null', () => {
    expect(divBadgeStyle(null)).toEqual({})
  })

  it('returns green style for low score', () => {
    const style = divBadgeStyle(0.1)
    expect(style.color).toBe('var(--green)')
  })

  it('returns red style for high score', () => {
    const style = divBadgeStyle(0.8)
    expect(style.color).toBe('var(--red)')
  })
})

describe('filterChip', () => {
  it('shows active style when true', () => {
    const chip = filterChip(true)
    expect(chip.color).toBe('var(--accent)')
    expect(chip.border).toContain('var(--accent)')
  })

  it('shows inactive style when false', () => {
    const chip = filterChip(false)
    expect(chip.color).toBe('var(--muted)')
  })
})

describe('branchChip', () => {
  it('returns A-colored chip', () => {
    const chip = branchChip('A')
    expect(chip.color).toBe('var(--accent)')
  })

  it('returns B-colored chip', () => {
    const chip = branchChip('B')
    expect(chip.color).toBe('var(--purple)')
  })
})

describe('hoverHandlers', () => {
  it('has onMouseEnter and onMouseLeave', () => {
    expect(typeof hoverHandlers.onMouseEnter).toBe('function')
    expect(typeof hoverHandlers.onMouseLeave).toBe('function')
  })
})
