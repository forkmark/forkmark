import '@testing-library/jest-dom'

// Mock window.location.hash for hash-based routing tests
Object.defineProperty(window, 'location', {
  value: {
    ...window.location,
    hash: '#dashboard',
  },
  writable: true,
})

// Suppress React 18 act() warnings in test output
const originalError = console.error
console.error = (...args) => {
  if (typeof args[0] === 'string' && args[0].includes('act(')) return
  originalError.call(console, ...args)
}
