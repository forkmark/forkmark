import { useState, useEffect } from 'react'
import { dispatchApiError } from '../api.js'
import {
  StatCard, EmptyState, PageHeader, SkeletonStatCards,
  pageStyle, tableStyles as T, formatNum,
} from './ui'

const S = {
  refresh:  { background:'transparent', border:'1px solid var(--border)', borderRadius:5,
              color:'var(--muted)', padding:'4px 12px', fontSize:11, cursor:'pointer', marginLeft:12 },
  grid:     { display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(220px, 1fr))', gap:12, marginBottom:24 },
  section:  { marginBottom:28 },
  sectionH: { fontSize:14, fontWeight:700, color:'var(--text)', marginBottom:12,
              paddingBottom:6, borderBottom:'1px solid var(--border)' },
  metricName:{ fontFamily:'var(--mono)', fontSize:11, wordBreak:'break-all' },
  barWrap:  { display:'flex', alignItems:'center', gap:6 },
  bar:      (pct, color) => ({
    height:6, borderRadius:3, width:`${Math.min(pct, 100)}%`, minWidth:2,
    background: color || 'var(--accent)',
  }),
}

function parseMetricName(key) {
  const match = key.match(/^([^{]+)\{?(.*)?\}?$/)
  if (!match) return { name: key, labels: {} }
  const name = match[1]
  const labels = {}
  if (match[2]) {
    for (const part of match[2].replace(/}$/, '').split(',')) {
      const [k, v] = part.split('=')
      if (k) labels[k.trim()] = (v || '').trim()
    }
  }
  return { name, labels }
}

export default function TracingDashboard() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLR]  = useState(null)

  async function load() {
    setLoading(true)
    try {
      const resp = await fetch('/metrics')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const d = await resp.json()
      setData(d)
      setLR(new Date())
    } catch (err) {
      dispatchApiError('Failed to load metrics: ' + (err.message || ''))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
  }, [])

  if (loading && !data) {
    return <div style={pageStyle(1200)}><SkeletonStatCards count={5} /></div>
  }

  const counters = data?.counters || {}
  const histograms = data?.histograms || {}

  const totalRequests = Object.entries(counters)
    .filter(([k]) => k.startsWith('http_requests_total'))
    .reduce((sum, [, v]) => sum + v, 0)
  const errorRequests = Object.entries(counters)
    .filter(([k]) => k.includes('status=5'))
    .reduce((sum, [, v]) => sum + v, 0)
  const errorRate = totalRequests > 0 ? (errorRequests / totalRequests * 100) : 0
  const reqLatency = histograms['http_request_duration_ms'] || null
  const scoringCount = Object.entries(counters)
    .filter(([k]) => k.includes('scoring'))
    .reduce((sum, [, v]) => sum + v, 0)

  return (
    <div style={pageStyle(1200)}>
      <PageHeader
        title="Observability Dashboard"
        subtitle={`Real-time metrics and tracing data${lastRefresh ? ` — last updated ${lastRefresh.toLocaleTimeString()}` : ''}`}
        right={<button style={S.refresh} onClick={load}>Refresh</button>}
      />

      <div style={S.grid}>
        <StatCard label="Total Requests" value={formatNum(totalRequests)} />
        <StatCard label="Error Rate"     value={`${errorRate.toFixed(1)}%`}
                  color={errorRate > 5 ? 'var(--red)' : errorRate > 1 ? 'var(--orange)' : 'var(--green)'} />
        <StatCard label="Avg Latency"    value={reqLatency ? `${reqLatency.avg.toFixed(0)}ms` : '—'} />
        <StatCard label="P95 Latency"    value={reqLatency ? `${reqLatency.p95.toFixed(0)}ms` : '—'}
                  color={reqLatency?.p95 > 2000 ? 'var(--red)' : undefined} />
        <StatCard label="Scoring Ops"    value={formatNum(scoringCount)} />
      </div>

      {Object.keys(counters).length > 0 && (
        <div style={S.section}>
          <div style={S.sectionH}>Counters</div>
          <table style={T.table}>
            <thead>
              <tr>
                <th style={T.th}>Metric</th>
                <th style={T.th}>Labels</th>
                <th style={T.th}>Value</th>
                <th style={{ ...T.th, width:'30%' }}>Relative</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(counters)
                .sort((a, b) => b[1] - a[1])
                .map(([key, val]) => {
                  const { name, labels } = parseMetricName(key)
                  const maxCount = Math.max(...Object.values(counters))
                  const pct = maxCount > 0 ? (val / maxCount) * 100 : 0
                  const isError = key.includes('status=5') || key.includes('error')
                  return (
                    <tr key={key}>
                      <td style={T.td}><span style={S.metricName}>{name}</span></td>
                      <td style={{ ...T.td, fontSize:10, color:'var(--muted)' }}>
                        {Object.entries(labels).map(([k, v]) => `${k}=${v}`).join(', ') || '—'}
                      </td>
                      <td style={{ ...T.td, fontWeight:600 }}>{formatNum(val)}</td>
                      <td style={T.td}>
                        <div style={S.barWrap}>
                          <div style={{ width:'100%', background:'var(--surface2)', borderRadius:3, height:6 }}>
                            <div style={S.bar(pct, isError ? 'var(--red)' : 'var(--accent)')} />
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                })}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(histograms).length > 0 && (
        <div style={S.section}>
          <div style={S.sectionH}>Latency Histograms</div>
          <table style={T.table}>
            <thead>
              <tr>
                <th style={T.th}>Metric</th>
                <th style={T.th}>Count</th>
                <th style={T.th}>Avg</th>
                <th style={T.th}>P50</th>
                <th style={T.th}>P95</th>
                <th style={T.th}>P99</th>
                <th style={T.th}>Max</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(histograms).map(([key, stats]) => {
                const { name } = parseMetricName(key)
                return (
                  <tr key={key}>
                    <td style={T.td}><span style={S.metricName}>{name}</span></td>
                    <td style={{ ...T.td, fontWeight:600 }}>{formatNum(stats.count)}</td>
                    <td style={T.td}>{stats.avg?.toFixed(1)}ms</td>
                    <td style={T.td}>{stats.p50?.toFixed(1)}ms</td>
                    <td style={{ ...T.td, color: stats.p95 > 2000 ? 'var(--red)' : 'var(--text)' }}>
                      {stats.p95?.toFixed(1)}ms
                    </td>
                    <td style={{ ...T.td, color: stats.p99 > 5000 ? 'var(--red)' : 'var(--text)' }}>
                      {stats.p99?.toFixed(1)}ms
                    </td>
                    <td style={T.td}>{stats.max?.toFixed(1)}ms</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(counters).length === 0 && Object.keys(histograms).length === 0 && (
        <EmptyState body="No metrics data yet. Metrics will appear as the API processes requests." />
      )}
    </div>
  )
}
