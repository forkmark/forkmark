import { useState, useMemo } from 'react'
import { tableStyles as TS, filterChip, hoverHandlers } from './styles.js'

/**
 * Reusable data table with sorting, filtering, and pagination.
 *
 * Props:
 *   columns     - array of { key, label, render?, sortable?, width? }
 *   data        - array of row objects
 *   onRowClick  - (row) => void
 *   pageSize    - rows per page (default 25, 0 = no pagination)
 *   emptyText   - text when data is empty
 *   filters     - optional array of { key, label, fn: (row) => bool }
 *   searchKey   - optional key to enable text search on that field
 *   searchPlaceholder - placeholder for search input
 *   compact     - use tighter padding (default false)
 */
export default function DataTable({
  columns,
  data,
  onRowClick,
  pageSize = 25,
  emptyText = 'No data',
  filters,
  searchKey,
  searchPlaceholder = 'Search...',
  compact = false,
}) {
  const [sortKey, setSortKey]       = useState(null)
  const [sortDir, setSortDir]       = useState('asc')
  const [activeFilter, setFilter]   = useState(null)
  const [search, setSearch]         = useState('')
  const [page, setPage]             = useState(0)

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
    setPage(0)
  }

  const processed = useMemo(() => {
    let rows = [...data]

    // Apply active filter
    if (activeFilter && filters) {
      const f = filters.find(f => f.key === activeFilter)
      if (f) rows = rows.filter(f.fn)
    }

    // Apply search
    if (search && searchKey) {
      const lower = search.toLowerCase()
      rows = rows.filter(r => String(r[searchKey] || '').toLowerCase().includes(lower))
    }

    // Apply sort
    if (sortKey) {
      rows.sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey]
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av
        return sortDir === 'asc'
          ? String(av).localeCompare(String(bv))
          : String(bv).localeCompare(String(av))
      })
    }

    return rows
  }, [data, activeFilter, filters, search, searchKey, sortKey, sortDir])

  const totalPages = pageSize > 0 ? Math.ceil(processed.length / pageSize) : 1
  const visible    = pageSize > 0 ? processed.slice(page * pageSize, (page + 1) * pageSize) : processed

  const tdPad = compact ? '7px 12px' : '10px 14px'

  return (
    <div>
      {/* Toolbar: filters + search */}
      {(filters || searchKey) && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          {filters && filters.map(f => (
            <button key={f.key} style={filterChip(activeFilter === f.key)}
                    onClick={() => { setFilter(activeFilter === f.key ? null : f.key); setPage(0) }}>
              {f.label}
            </button>
          ))}
          {searchKey && (
            <input
              style={{
                background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 5,
                color: 'var(--text)', padding: '5px 10px', fontSize: 12, fontFamily: 'var(--font)', minWidth: 180,
              }}
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(0) }}
              placeholder={searchPlaceholder}
            />
          )}
          <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 'auto' }}>
            {processed.length} result{processed.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}

      {visible.length === 0 ? (
        <div style={{ padding: 32, color: 'var(--muted)', textAlign: 'center', fontSize: 13 }}>{emptyText}</div>
      ) : (
        <table style={TS.table}>
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col.key}
                    style={{ ...TS.th, width: col.width, cursor: col.sortable ? 'pointer' : 'default', userSelect: 'none' }}
                    onClick={col.sortable ? () => handleSort(col.key) : undefined}>
                  {col.label}
                  {col.sortable && sortKey === col.key && (
                    <span style={{ marginLeft: 4, fontSize: 10 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={row.id || i}
                  style={onRowClick ? TS.row : {}}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  {...(onRowClick ? hoverHandlers : {})}
              >
                {columns.map(col => (
                  <td key={col.key} style={{ ...TS.td, padding: tdPad }}>
                    {col.render ? col.render(row, i) : (row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Pagination */}
      {pageSize > 0 && totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, marginTop: 12, fontSize: 12 }}>
          <button
            style={{ ...pageBtnStyle, opacity: page === 0 ? 0.4 : 1 }}
            disabled={page === 0}
            onClick={() => setPage(p => p - 1)}
          >
            ← Prev
          </button>
          <span style={{ color: 'var(--muted)' }}>
            Page {page + 1} of {totalPages}
          </span>
          <button
            style={{ ...pageBtnStyle, opacity: page >= totalPages - 1 ? 0.4 : 1 }}
            disabled={page >= totalPages - 1}
            onClick={() => setPage(p => p + 1)}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}

const pageBtnStyle = {
  fontSize: 12, padding: '4px 12px',
  background: 'transparent', color: 'var(--accent)',
  border: '1px solid var(--border)', borderRadius: 5, cursor: 'pointer',
}
