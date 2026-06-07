import { Component } from 'react'

const S = {
  wrap:  { padding: 32, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200 },
  box:   { maxWidth: 520, textAlign: 'center' },
  icon:  { fontSize: 32, marginBottom: 12 },
  h:     { fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 8 },
  msg:   { fontSize: 13, color: 'var(--muted)', marginBottom: 20, lineHeight: 1.6 },
  pre:   { fontSize: 11, color: 'var(--muted)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, padding: '10px 14px', textAlign: 'left', overflowX: 'auto', maxHeight: 140, whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginBottom: 20 },
  btn:   { fontSize: 13, padding: '7px 18px', background: 'var(--accent)', color: 'var(--bg)', border: 'none', borderRadius: 5, fontWeight: 700, cursor: 'pointer' },
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    this.setState({ info })
    // Emit to console so it's still visible in DevTools
    console.error('[ErrorBoundary]', error, info)
  }

  reset() {
    this.setState({ error: null, info: null })
  }

  render() {
    const { error, info } = this.state
    if (!error) return this.props.children

    const stack = info?.componentStack?.trim() || ''
    const label = this.props.label || 'This panel'

    return (
      <div style={S.wrap}>
        <div style={S.box}>
          <div style={S.icon}>⚠</div>
          <div style={S.h}>{label} ran into a problem</div>
          <div style={S.msg}>
            {error.message || 'An unexpected error occurred.'}
            {' '}The rest of the app is still working.
          </div>
          {stack && (
            <pre style={S.pre}>{stack}</pre>
          )}
          <button style={S.btn} onClick={() => this.reset()}>Try again</button>
        </div>
      </div>
    )
  }
}
