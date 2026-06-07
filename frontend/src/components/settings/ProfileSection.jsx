import { useState } from 'react'
import { S, COMMON_TIMEZONES, Toggle } from './shared.jsx'

export default function ProfileSection({
  displayName, setDisplayName, timezone, setTimezone,
  theme, onThemeChange,
  notifToast, setNotifToast, notifBrowser, setNotifBrowser,
  notifDismiss, setNotifDismiss,
}) {
  const [focused, setFocused] = useState(null)

  return (
    <>
      {/* ─── SECTION: User Profile ─── */}
      <div style={S.section}>User Profile</div>

      <div style={S.card}>
        <h2 style={S.cardH}>Profile</h2>
        <p style={S.cardSub}>Your identity and display preferences within the platform.</p>

        <div style={S.row}>
          <label htmlFor="settings-display-name" style={S.label}>Display Name</label>
          <input
            id="settings-display-name"
            style={{ ...S.input, borderColor: focused === 'name' ? 'var(--accent)' : 'var(--border)' }}
            placeholder="e.g. Alice Chen"
            value={displayName}
            onChange={e => setDisplayName(e.target.value)}
            onFocus={() => setFocused('name')}
            onBlur={() => setFocused(null)}
          />
          <p style={S.hint}>Shown in decision history, comments, and review assignments.</p>
        </div>

        <div style={S.row}>
          <label htmlFor="settings-timezone" style={S.label}>Timezone</label>
          <select
            id="settings-timezone"
            style={{ ...S.input }}
            value={timezone}
            onChange={e => setTimezone(e.target.value)}
          >
            <option value="">Browser default</option>
            {COMMON_TIMEZONES.filter(Boolean).map(tz => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </select>
          <p style={S.hint}>Used for displaying timestamps in the Tracing Dashboard and Decision History.</p>
        </div>
      </div>

      {/* ─── SECTION: Appearance ─── */}
      <div style={S.section}>Appearance</div>

      <div style={S.card}>
        <h2 style={S.cardH}>Theme</h2>
        <p style={S.cardSub}>Switch between dark and light mode. Applied instantly.</p>

        <div style={{ display:'flex', gap:8 }}>
          {['dark', 'light'].map(t => (
            <button
              key={t}
              style={{
                ...S.btn(theme === t, false),
                flex:1, textAlign:'center',
                background: theme === t ? 'var(--accent)' : 'var(--bg)',
                color: theme === t ? 'var(--bg)' : 'var(--text)',
                border: `1px solid ${theme === t ? 'var(--accent)' : 'var(--border)'}`,
                textTransform:'capitalize',
              }}
              onClick={() => onThemeChange(t)}
            >
              {t === 'dark' ? '● Dark' : '○ Light'}
            </button>
          ))}
        </div>
      </div>

      {/* ─── SECTION: Notifications ─── */}
      <div style={S.section}>Notifications</div>

      <div style={S.card}>
        <h2 style={S.cardH}>Notification Preferences</h2>
        <p style={S.cardSub}>Control how Forkmark notifies you about eval runs, scoring, and errors.</p>

        <div style={S.toggleRow}>
          <div>
            <div style={S.toggleLabel}>Toast notifications</div>
            <div style={S.toggleHint}>Show in-app toast messages for success, errors, and status updates</div>
          </div>
          <Toggle on={notifToast} onChange={setNotifToast} label="Toggle toast notifications" />
        </div>

        <div style={{ ...S.toggleRow, borderBottom: 'none' }}>
          <div>
            <div style={S.toggleLabel}>Browser notifications</div>
            <div style={S.toggleHint}>Send desktop notifications when eval runs complete (requires browser permission)</div>
          </div>
          <Toggle on={notifBrowser} label="Toggle browser notifications" onChange={v => {
            if (v && typeof Notification !== 'undefined' && Notification.permission === 'default') {
              Notification.requestPermission().then(p => setNotifBrowser(p === 'granted'))
            } else {
              setNotifBrowser(v)
            }
          }} />
        </div>

        <div style={{ ...S.row, marginTop:16 }}>
          <label htmlFor="settings-dismiss-time" style={S.label}>Auto-dismiss after (seconds)</label>
          <div style={S.rangeRow}>
            <input id="settings-dismiss-time" style={S.range} type="range" min="2" max="15" step="1"
                   value={notifDismiss} onChange={e => setNotifDismiss(parseInt(e.target.value))} />
            <span style={S.rangeVal}>{notifDismiss}s</span>
          </div>
          <p style={S.hint}>How long toast messages stay visible before auto-dismissing.</p>
        </div>
      </div>
    </>
  )
}
