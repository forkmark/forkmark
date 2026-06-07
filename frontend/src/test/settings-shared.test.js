import { describe, it, expect } from 'vitest'
import { S, Toggle, DEFAULT_MODELS, SCORER_OPTIONS, COMMON_TIMEZONES } from '../components/settings/shared.jsx'

describe('Settings shared constants', () => {
  it('DEFAULT_MODELS contains expected models', () => {
    expect(DEFAULT_MODELS).toContain('gpt-4o')
    expect(DEFAULT_MODELS).toContain('gpt-4o-mini')
    expect(DEFAULT_MODELS.length).toBeGreaterThan(3)
  })

  it('SCORER_OPTIONS has auto as first option', () => {
    expect(SCORER_OPTIONS[0].value).toBe('auto')
  })

  it('COMMON_TIMEZONES includes major zones', () => {
    expect(COMMON_TIMEZONES).toContain('America/New_York')
    expect(COMMON_TIMEZONES).toContain('Europe/London')
    expect(COMMON_TIMEZONES).toContain('Asia/Tokyo')
  })
})

describe('Settings shared styles (S)', () => {
  it('card has background and border', () => {
    expect(S.card.background).toBeDefined()
    expect(S.card.border).toBeDefined()
    expect(S.card.borderRadius).toBe(8)
  })

  it('badge returns different styles based on set/unset', () => {
    const set = S.badge(true)
    const unset = S.badge(false)
    expect(set.color).not.toBe(unset.color)
    expect(set.background).not.toBe(unset.background)
  })

  it('btn returns primary style', () => {
    const primary = S.btn(true, false)
    expect(primary.background).toBe('var(--accent)')
  })

  it('btn returns disabled style', () => {
    const disabled = S.btn(true, true)
    expect(disabled.opacity).toBe(0.6)
    expect(disabled.cursor).toBe('not-allowed')
  })

  it('toggle returns different styles based on on/off', () => {
    const on = S.toggle(true)
    const off = S.toggle(false)
    expect(on.background).toBe('var(--green)')
    expect(off.background).toBe('var(--border)')
  })

  it('toggleDot moves based on on/off', () => {
    const on = S.toggleDot(true)
    const off = S.toggleDot(false)
    expect(on.left).toBe(18)
    expect(off.left).toBe(2)
  })

  it('section has uppercase text transform', () => {
    expect(S.section.textTransform).toBe('uppercase')
  })

  it('featureBadge returns different styles based on on/off', () => {
    const on = S.featureBadge(true)
    const off = S.featureBadge(false)
    expect(on.color).toBe('var(--green)')
    expect(off.color).toBe('var(--muted)')
  })
})

describe('Toggle component', () => {
  it('is defined and is a function', () => {
    expect(typeof Toggle).toBe('function')
  })
})
