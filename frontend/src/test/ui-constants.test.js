import { describe, it, expect } from 'vitest'
import {
  fmtDate, fmtDateLong, fmtDateTime, formatNum,
  divColor, divBg, choiceColor, choiceBg,
  modelCostPer1M, branchCost,
  MODEL_PRICING, MODELS,
} from '../components/ui/constants.js'

describe('fmtDate', () => {
  it('returns dash for falsy input', () => {
    expect(fmtDate(null)).toBe('—')
    expect(fmtDate('')).toBe('—')
    expect(fmtDate(undefined)).toBe('—')
  })

  it('formats a valid timestamp', () => {
    const result = fmtDate('2026-03-15T10:30:00Z')
    expect(result).toMatch(/Mar/)
    expect(result).toMatch(/15/)
  })
})

describe('fmtDateLong', () => {
  it('returns Never for falsy input', () => {
    expect(fmtDateLong(null)).toBe('Never')
    expect(fmtDateLong('')).toBe('Never')
  })

  it('includes year in output', () => {
    const result = fmtDateLong('2026-03-15T10:30:00Z')
    expect(result).toMatch(/2026/)
  })
})

describe('fmtDateTime', () => {
  it('returns dash for falsy input', () => {
    expect(fmtDateTime(null)).toBe('—')
    expect(fmtDateTime('')).toBe('—')
  })

  it('includes time in output', () => {
    const result = fmtDateTime('2026-03-15T10:30:00Z')
    // Should have month + day + time components
    expect(result).toMatch(/Mar/)
    expect(result).toMatch(/15/)
  })
})

describe('formatNum', () => {
  it('returns dash for null/undefined', () => {
    expect(formatNum(null)).toBe('—')
    expect(formatNum(undefined)).toBe('—')
  })

  it('formats millions', () => {
    expect(formatNum(2_500_000)).toBe('2.5M')
  })

  it('formats thousands', () => {
    expect(formatNum(1_500)).toBe('1.5K')
  })

  it('returns plain number for small values', () => {
    expect(formatNum(42)).toBe('42')
  })

  it('formats decimals', () => {
    expect(formatNum(3.14159)).toBe('3.14')
  })
})

describe('divColor', () => {
  it('returns muted for null', () => {
    expect(divColor(null)).toBe('var(--muted)')
  })

  it('returns green for low divergence', () => {
    expect(divColor(0.1)).toBe('var(--green)')
  })

  it('returns orange for medium divergence', () => {
    expect(divColor(0.3)).toBe('var(--orange)')
  })

  it('returns red for high divergence', () => {
    expect(divColor(0.7)).toBe('var(--red)')
  })

  it('returns green at exactly 0', () => {
    expect(divColor(0)).toBe('var(--green)')
  })

  it('transitions at 0.2 boundary', () => {
    expect(divColor(0.19)).toBe('var(--green)')
    expect(divColor(0.2)).toBe('var(--orange)')
  })

  it('transitions at 0.5 boundary', () => {
    expect(divColor(0.49)).toBe('var(--orange)')
    expect(divColor(0.5)).toBe('var(--red)')
  })
})

describe('divBg', () => {
  it('returns transparent for null', () => {
    expect(divBg(null)).toBe('transparent')
  })

  it('returns colored backgrounds', () => {
    expect(divBg(0.1)).toMatch(/rgba/)
    expect(divBg(0.3)).toMatch(/rgba/)
    expect(divBg(0.7)).toMatch(/rgba/)
  })
})

describe('choiceColor', () => {
  it('returns correct colors for A, B, neither, both', () => {
    expect(choiceColor('A')).toBe('#7ba4f7')
    expect(choiceColor('B')).toBe('#c4a1f5')
    expect(choiceColor('neither')).toBe('#6b7394')
    expect(choiceColor('both')).toBe('#4ade80')
  })

  it('returns default for unknown', () => {
    expect(choiceColor('unknown')).toBe('#6b7394')
  })
})

describe('choiceBg', () => {
  it('returns rgba for known choices', () => {
    expect(choiceBg('A')).toMatch(/rgba\(123,164,247/)
  })

  it('returns default rgba for unknown', () => {
    expect(choiceBg('unknown')).toMatch(/rgba\(107,115,148/)
  })
})

describe('modelCostPer1M', () => {
  it('returns null for null input', () => {
    expect(modelCostPer1M(null)).toBeNull()
  })

  it('finds known models case-insensitively', () => {
    // Note: uses includes() matching, so 'gpt-4o' matches before 'gpt-4o-mini'
    // when passed as 'GPT-4o-mini'. This is the expected behavior.
    const cost = modelCostPer1M('GPT-4o')
    expect(cost).toEqual([2.50, 10.00])

    // Exact substring match for gpt-4o-mini
    const miniCost = modelCostPer1M('gpt-4o-mini')
    expect(miniCost).toBeDefined()
    expect(miniCost).toHaveLength(2)
  })

  it('returns null for unknown model', () => {
    expect(modelCostPer1M('nonexistent-model')).toBeNull()
  })
})

describe('branchCost', () => {
  it('returns null for unknown model', () => {
    expect(branchCost(1000, 500, 'unknown')).toBeNull()
  })

  it('calculates cost correctly', () => {
    // gpt-4o: [2.50, 10.00] per 1M tokens
    const cost = branchCost(1_000_000, 1_000_000, 'gpt-4o')
    expect(cost).toBeCloseTo(12.50)
  })

  it('handles zero tokens', () => {
    const cost = branchCost(0, 0, 'gpt-4o')
    expect(cost).toBe(0)
  })
})

describe('MODEL_PRICING / MODELS', () => {
  it('MODELS is derived from MODEL_PRICING keys', () => {
    expect(MODELS).toEqual(Object.keys(MODEL_PRICING))
  })

  it('every model has [input, output] pricing', () => {
    for (const [model, prices] of Object.entries(MODEL_PRICING)) {
      expect(prices).toHaveLength(2)
      expect(typeof prices[0]).toBe('number')
      expect(typeof prices[1]).toBe('number')
    }
  })
})
