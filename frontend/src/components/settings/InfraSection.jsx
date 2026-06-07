import { S } from './shared.jsx'

export default function InfraSection({
  saving,
  storage, restartNeeded,
  currentWorkers, selectedWorkers, setSelectedWorkers,
  enterprise,
  onSaveSystemInfo,
}) {
  const workersChanged = selectedWorkers !== currentWorkers

  return (
    <>
      <div style={S.section}>Infrastructure</div>

      {/* Storage Card (read-only indicator) */}
      <div style={S.card}>
        <h2 style={S.cardH}>Storage</h2>
        <p style={S.cardSub}>
          Forkmark uses SQLite by default. For production and teams, set
          <code> FM_DATABASE_URL</code> to a PostgreSQL connection string.
        </p>
        <div style={S.row}>
          <span style={S.badge(true)}>
            <span style={S.dot(true)} />
            {storage === 'postgresql' ? 'PostgreSQL' : 'SQLite'}
          </span>
        </div>
      </div>

      {/* Background Workers Card */}
      <div style={S.card}>
        <h2 style={S.cardH}>Background Workers</h2>
        <p style={S.cardSub}>
          Number of background threads for divergence scoring and evaluation.
          More workers = faster batch processing, but higher resource usage. Requires restart.
        </p>

        <div style={S.row}>
          <label htmlFor="settings-workers" style={S.label}>Worker Threads</label>
          <div style={S.rangeRow}>
            <input id="settings-workers" style={S.range} type="range" min="1" max="16" step="1"
                   value={selectedWorkers}
                   onChange={e => setSelectedWorkers(parseInt(e.target.value))} />
            <span style={S.rangeVal}>{selectedWorkers}</span>
          </div>
          <p style={S.hint}>
            Current: {currentWorkers} thread{currentWorkers !== 1 ? 's' : ''}.
            {selectedWorkers <= 2 && ' Low — suitable for constrained environments.'}
            {selectedWorkers > 2 && selectedWorkers <= 8 && ' Balanced — good for most workloads.'}
            {selectedWorkers > 8 && ' High — best for large batch evaluations.'}
          </p>
        </div>

        {workersChanged && !restartNeeded && (
          <div style={S.footer}>
            <button
              style={S.btn(true, saving)}
              disabled={saving}
              onClick={() => onSaveSystemInfo({ background_workers: selectedWorkers })}
            >
              {saving ? 'Saving…' : 'Apply & Restart Required'}
            </button>
            <button
              style={S.btn(false, false)}
              onClick={() => setSelectedWorkers(currentWorkers)}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* Enterprise Features Card */}
      <div style={S.card}>
        <h2 style={S.cardH}>
          Platform Status
          <span style={{ marginLeft:8, fontSize:10, padding:'2px 8px', borderRadius:10, fontWeight:700,
            background: enterprise.multi_tenant ? 'rgba(196,161,245,0.15)' : 'rgba(74,222,128,0.15)',
            color: enterprise.multi_tenant ? 'var(--purple)' : 'var(--green)' }}>
            {enterprise.multi_tenant ? 'Enterprise' : 'Community Edition'}
          </span>
        </h2>
        <p style={S.cardSub}>
          {enterprise.multi_tenant
            ? 'Enterprise and infrastructure features. Configured via environment variables or Kubernetes ConfigMap.'
            : 'You are running the open-source Community Edition — the full comparison, human-review, and DPO-export workflow. Team and security features (multi-tenancy, SSO/SCIM, audit-log retention) are part of the upcoming Forkmark Enterprise edition and are not included in this build.'}
        </p>

        {[
          ['UI Authentication (FM_REQUIRE_UI_AUTH)', enterprise.require_ui_auth, v => v ? 'Enabled' : 'Disabled'],
          ['Multi-Tenant Mode',                      enterprise.multi_tenant,     v => v ? 'Active' : 'Single-tenant'],
          ['SCIM Provisioning',                      enterprise.scim_enabled,     v => v ? 'Enabled' : 'Off'],
          ['Device Flow Auth',                       enterprise.device_flow_enabled, v => v ? 'Enabled' : 'Off'],
          ['OpenTelemetry',                          enterprise.otel_enabled,     v => v ? 'Active' : 'Off'],
        ].map(([name, on, fmt]) => (
          <div key={name} style={S.featureRow}>
            <span style={S.featureName}>{name}</span>
            <span style={S.featureBadge(on)}>{fmt(on)}</span>
          </div>
        ))}

        <p style={{ ...S.hint, marginTop:12 }}>
          UI authentication is controlled by the <code>FM_REQUIRE_UI_AUTH</code> environment variable
          (it&rsquo;s required automatically when the server is not bound to localhost). The remaining
          rows reflect Enterprise capabilities, which are not bundled with the Community Edition.
        </p>
      </div>
    </>
  )
}
