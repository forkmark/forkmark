// ── Settings shared constants, styles, and sub-components ──────────────────

export const DEFAULT_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4-turbo',
  'gpt-3.5-turbo',
  'openai/gpt-4o',
  'anthropic/claude-3-5-sonnet',
  'google/gemini-pro-1.5',
]

export const SCORER_OPTIONS = [
  { value: 'auto',      label: 'Auto (Recommended)', recommended: true,
    desc: 'Picks the best available method automatically — good for most teams',
    detail: 'Uses semantic scoring if sentence-transformers is installed, otherwise falls back to lexical' },
  { value: 'lexical',   label: 'Lexical — Fast & Free',
    desc: 'Compares text character-by-character — instant, no setup needed',
    detail: 'TF-IDF cosine + SequenceMatcher — zero dependencies, ~1ms per comparison' },
  { value: 'semantic',  label: 'Semantic — Better Accuracy',
    desc: 'Understands meaning, not just words — catches paraphrases',
    detail: 'sentence-transformers all-MiniLM-L6-v2 — ~50ms, 80MB model download', dep: 'pip install sentence-transformers' },
  { value: 'openai',    label: 'OpenAI Embeddings',
    desc: 'High-quality similarity using OpenAI — requires API key',
    detail: 'text-embedding-3-small cosine distance — ~$0.0001 per comparison', dep: 'API key required' },
  { value: 'llm_judge', label: 'LLM Judge — Most Accurate',
    desc: 'An AI model grades quality — best results, ~$0.001 per comparison',
    detail: 'G-Eval LLM-as-judge with structured rubric — 2–5s per comparison', dep: 'API key required' },
]

export const COMMON_TIMEZONES = [
  '', 'UTC',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Anchorage', 'Pacific/Honolulu', 'America/Toronto', 'America/Vancouver',
  'Europe/London', 'Europe/Berlin', 'Europe/Paris', 'Europe/Moscow',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata', 'Asia/Singapore',
  'Australia/Sydney', 'Pacific/Auckland',
]

// ── Local styles specific to Settings (not in ui/) ──────────────────────────

export const S = {
  card:    { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:24, marginBottom:24 },
  cardH:   { fontSize:15, fontWeight:600, color:'var(--text)', margin:'0 0 4px 0' },
  cardSub: { fontSize:12, color:'var(--muted)', margin:'0 0 20px 0' },

  row:     { marginBottom:16 },
  label:   { display:'block', fontSize:12, fontWeight:500, color:'var(--muted)', marginBottom:6, textTransform:'uppercase', letterSpacing:'0.5px' },
  input:   {
    width:'100%', boxSizing:'border-box',
    background:'var(--bg)', border:'1px solid var(--border)',
    borderRadius:6, padding:'9px 12px', fontSize:13,
    color:'var(--text)', outline:'none',
  },
  hint:    { fontSize:11, color:'var(--muted)', marginTop:4 },

  badge:   (set) => ({
    display:'inline-flex', alignItems:'center', gap:5,
    fontSize:11, padding:'3px 8px', borderRadius:4,
    background: set ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.1)',
    color: set ? 'var(--green)' : 'var(--red)',
    border: `1px solid ${set ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.25)'}`,
  }),
  dot:     (set) => ({
    width:6, height:6, borderRadius:'50%',
    background: set ? 'var(--green)' : 'var(--red)',
  }),

  footer:  { display:'flex', alignItems:'center', gap:12, marginTop:20 },
  btn:     (primary, disabled) => ({
    padding:'9px 18px', borderRadius:6, fontSize:13, fontWeight:500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    background: disabled ? 'var(--border)'
               : primary  ? 'var(--accent)' : 'var(--surface)',
    color: disabled ? 'var(--muted)'
           : primary ? 'var(--bg)' : 'var(--text)',
    border: primary ? 'none' : '1px solid var(--border)',
    opacity: disabled ? 0.6 : 1,
  }),

  // Restart banner
  banner:  {
    display:'flex', alignItems:'center', gap:10,
    background:'rgba(251,191,36,0.1)', border:'1px solid rgba(251,191,36,0.3)',
    borderRadius:8, padding:'12px 16px', marginBottom:24,
    fontSize:13, color:'var(--orange)',
  },
  bannerIcon: { fontSize:18, flexShrink:0 },

  // Toggle switch
  toggle: (on) => ({
    width:36, height:20, borderRadius:10, cursor:'pointer', border:'none',
    background: on ? 'var(--green)' : 'var(--border)', position:'relative',
    transition:'background 0.2s', flexShrink:0,
  }),
  toggleDot: (on) => ({
    width:16, height:16, borderRadius:'50%', background:'#fff',
    position:'absolute', top:2, left: on ? 18 : 2,
    transition:'left 0.2s',
  }),

  toggleRow: {
    display:'flex', alignItems:'center', justifyContent:'space-between',
    padding:'10px 0', borderBottom:'1px solid var(--border)',
  },
  toggleLabel: { fontSize:13, color:'var(--text)' },
  toggleHint:  { fontSize:11, color:'var(--muted)', marginTop:2 },

  // Range slider
  rangeRow: { display:'flex', alignItems:'center', gap:12 },
  range:    { flex:1, accentColor:'var(--accent)' },
  rangeVal: { fontSize:13, color:'var(--text)', fontWeight:600, minWidth:28, textAlign:'right' },

  // Section divider
  section: { fontSize:11, fontWeight:700, color:'var(--accent)', textTransform:'uppercase', letterSpacing:'0.8px', margin:'28px 0 16px', paddingBottom:8, borderBottom:'1px solid var(--border)' },

  // Enterprise feature row
  featureRow: {
    display:'flex', alignItems:'center', justifyContent:'space-between',
    padding:'8px 0',
  },
  featureName: { fontSize:13, color:'var(--text)' },
  featureBadge: (on) => ({
    fontSize:10, fontWeight:700, padding:'2px 8px', borderRadius:4,
    background: on ? 'rgba(74,222,128,0.12)' : 'rgba(107,115,148,0.12)',
    color: on ? 'var(--green)' : 'var(--muted)',
    border: `1px solid ${on ? 'rgba(74,222,128,0.3)' : 'rgba(107,115,148,0.25)'}`,
  }),
}

// ── Toggle component ────────────────────────────────────────────────────────

export function Toggle({ on, onChange, label }) {
  return (
    <button style={S.toggle(on)} onClick={() => onChange(!on)} type="button" aria-pressed={on} aria-label={label}>
      <span style={S.toggleDot(on)} />
    </button>
  )
}
