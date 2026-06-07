/**
 * Forkmark API client.
 *
 * API key management:
 *   - Stored in sessionStorage under "fm_active_key"
 *     (sessionStorage is cleared when the browser tab/window closes, reducing
 *      the XSS attack window compared to localStorage)
 *   - Sent as X-API-Key header on all write operations (POST/PATCH/DELETE)
 *   - Read operations are unauthenticated (GET)
 *   - Use setActiveKey(raw) / getActiveKey() / clearActiveKey() to manage
 *
 * Error handling:
 *   All API methods throw ApiError on non-2xx responses. Components should
 *   wrap calls in try/catch and call dispatchApiError(msg) to show a toast.
 */

const BASE = '/api'

// ── Key management ────────────────────────────────────────────────────────────

export const getActiveKey   = ()    => sessionStorage.getItem('fm_active_key') || ''
export const setActiveKey   = (key) => sessionStorage.setItem('fm_active_key', key)
export const clearActiveKey = ()    => sessionStorage.removeItem('fm_active_key')

// ── Reviewer identity (persisted in sessionStorage) ───────────────────────────

export const getReviewerId = ()    => sessionStorage.getItem('fm_reviewer_id') || ''
export const setReviewerId = (id)  => sessionStorage.setItem('fm_reviewer_id', id)

// ── Global error event ────────────────────────────────────────────────────────
// Components can listen for 'fp:apierror' on window to show toast messages.

export function dispatchApiError(message, action) {
  window.dispatchEvent(new CustomEvent('fp:apierror', { detail: { message, action } }))
}

/**
 * Enhance raw API error messages with actionable hints.
 * Called automatically by the error handler; also usable by components directly.
 */
export function enrichErrorMessage(msg) {
  const lower = (msg || '').toLowerCase()
  if (lower.includes('api key') && (lower.includes('not configured') || lower.includes('not set') || lower.includes('missing') || lower.includes('required'))) {
    return { message: msg, action: { label: 'Go to Settings', hash: '#settings' } }
  }
  if (lower.includes('openai') && (lower.includes('key') || lower.includes('auth'))) {
    return { message: msg, action: { label: 'Go to Settings', hash: '#settings' } }
  }
  if (lower.includes('not found') && lower.includes('eval')) {
    return { message: msg, action: { label: 'Back to Results', hash: '#evalRuns' } }
  }
  if (lower.includes('not found') && lower.includes('workflow')) {
    return { message: msg, action: { label: 'Back to Workflows', hash: '#workflow' } }
  }
  if (lower.includes('not found') && lower.includes('comparison')) {
    return { message: msg, action: { label: 'Back to Results', hash: '#evalRuns' } }
  }
  if (lower.includes('unauthorized') || lower.includes('forbidden') || lower.includes('invalid key')) {
    return { message: msg, action: { label: 'Check API Keys', hash: '#keys' } }
  }
  return { message: msg }
}

// ── Error class ───────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name   = 'ApiError'
    this.status = status
  }
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

const writeHeaders = () => {
  const key = getActiveKey()
  return {
    'Content-Type': 'application/json',
    ...(key ? { 'X-API-Key': key } : {}),
  }
}

async function _json(resp) {
  if (resp.status === 204) return null

  let body = null
  const ct = resp.headers.get('content-type') || ''
  if (ct.includes('application/json') || ct.includes('ndjson')) {
    body = await resp.json().catch(() => null)
  }

  if (!resp.ok) {
    const msg = body?.detail || body?.message || `HTTP ${resp.status}`
    throw new ApiError(msg, resp.status)
  }

  return body
}

const get = (p, q = {}) => {
  const qs = new URLSearchParams(q).toString()
  return fetch(`${BASE}${p}${qs ? '?' + qs : ''}`).then(_json)
}

// Like get() but always sends X-API-Key — required for auth-protected GET endpoints.
const authGet = (p, q = {}) => {
  const qs  = new URLSearchParams(q).toString()
  const key = getActiveKey()
  return fetch(`${BASE}${p}${qs ? '?' + qs : ''}`,
    { headers: key ? { 'X-API-Key': key } : {} }).then(_json)
}

const post  = (p, b)  => fetch(`${BASE}${p}`, { method: 'POST',   headers: writeHeaders(), body: JSON.stringify(b) }).then(_json)
const patch = (p, b)  => fetch(`${BASE}${p}`, { method: 'PATCH',  headers: writeHeaders(), body: JSON.stringify(b) }).then(_json)
const del   = (p)     => fetch(`${BASE}${p}`, { method: 'DELETE', headers: writeHeaders() }).then(_json)

// ── API surface ───────────────────────────────────────────────────────────────

export const api = {
  stats:              ()              => get('/stats'),
  statsCharts:        ()              => get('/stats/charts'),

  // tags
  listTags:           (wid)           => get('/tags', wid ? { workflow_id: wid } : {}),

  // workflows
  listWorkflows:      ()              => get('/workflows'),
  getWorkflow:        id              => get(`/workflows/${id}`),
  createWorkflow:     b               => post('/workflows', b),
  deleteWorkflow:     id              => del(`/workflows/${id}`),
  listRuns:           (wid, n)        => get(`/workflows/${wid}/runs`, { limit: n || 50 }),
  getRun:             id              => get(`/runs/${id}`),

  // ── eval runs ────────────────────────────────────────────────────────────
  listEvalRuns:       (wid)           => get('/eval-runs', wid ? { workflow_id: wid } : {}),
  createEvalRun:      b               => post('/eval-runs', b),
  getEvalRun:         id              => get(`/eval-runs/${id}`),
  deleteEvalRun:      id              => del(`/eval-runs/${id}`),
  exportEvalRun:      id              => `/api/eval-runs/${id}/export`,

  // ── test sets ─────────────────────────────────────────────────────────────
  listTestSets:       (wid)           => get('/test-sets', wid ? { workflow_id: wid } : {}),
  createTestSet:      b               => post('/test-sets', b),
  getTestSet:         id              => get(`/test-sets/${id}`),
  deleteTestSet:      id              => del(`/test-sets/${id}`),
  addTestCase:        (tsId, b)       => post(`/test-sets/${tsId}/cases`, b),
  bulkAddTestCases:   (tsId, cases)   => post(`/test-sets/${tsId}/cases/bulk`, { cases }),
  deleteTestCase:     (tsId, tcId)    => del(`/test-sets/${tsId}/cases/${tcId}`),

  // ── comparisons ───────────────────────────────────────────────────────────
  listComparisons:    (wid, undecided, erId, limit, offset) =>
                        get('/comparisons', {
                          ...(wid       ? { workflow_id:    wid    } : {}),
                          ...(undecided ? { undecided_only: true   } : {}),
                          ...(erId      ? { eval_run_id:    erId   } : {}),
                          ...(limit     ? { limit                  } : {}),
                          ...(offset    ? { offset                 } : {}),
                        }),
  getComparison:      id              => get(`/comparisons/${id}`),
  recordDecision:     (id, b)         => post(`/comparisons/${id}/decide`, b),
  updateDecision:     (id, b)         => patch(`/comparisons/${id}/decide`, b),

  // ── decisions ─────────────────────────────────────────────────────────────
  listDecisions:      (wid, erId, lim, offset) => get('/decisions', {
                          ...(wid    ? { workflow_id:  wid    } : {}),
                          ...(erId   ? { eval_run_id:  erId   } : {}),
                          ...(lim    ? { limit:        lim    } : {}),
                          ...(offset ? { offset               } : {}),
                        }),
  exportDecisions:    (wid, erId, fmt) => `/api/decisions/export?${new URLSearchParams({
                          ...(wid  ? { workflow_id:  wid  } : {}),
                          ...(erId ? { eval_run_id:  erId } : {}),
                          ...(fmt  ? { format:       fmt  } : {}),
                        })}`,
  exportDpo:          (wid, erId, opts) => `/api/decisions/export/dpo?${new URLSearchParams({
                          ...(wid  ? { workflow_id:  wid  } : {}),
                          ...(erId ? { eval_run_id:  erId } : {}),
                          ...(opts?.min_confidence ? { min_confidence: opts.min_confidence } : {}),
                          ...(opts?.min_divergence != null ? { min_divergence: opts.min_divergence } : {}),
                        })}`,
  exportOpenAiFt:     (wid, erId) => `/api/decisions/export/openai-ft?${new URLSearchParams({
                          ...(wid  ? { workflow_id:  wid  } : {}),
                          ...(erId ? { eval_run_id:  erId } : {}),
                        })}`,

  // ── providers ─────────────────────────────────────────────────────────────
  listProviders:    ()              => authGet('/providers'),
  createProvider:   b               => post('/providers', b),
  updateProvider:   (id, b)         => patch(`/providers/${id}`, b),
  deleteProvider:   id              => del(`/providers/${id}`),
  testProvider:     id              => post(`/providers/${id}/test`, {}),

  // ── keys ──────────────────────────────────────────────────────────────────
  listKeys:           ()              => authGet('/keys'),
  createKey:          b               => post('/keys', b),
  revokeKey:          id              => del(`/keys/${id}`),

  // ── settings ──────────────────────────────────────────────────────────────
  getSettings:        ()              => get('/settings'),
  patchSettings:      b               => patch('/settings', b),

  // ── system info ──────────────────────────────────────────────────────────
  getSystemInfo:      ()              => get('/system-info'),
  patchSystemInfo:    b               => patch('/system-info', b),

  // ── no-code runner ────────────────────────────────────────────────────────
  runWorkflow:        b               => post('/runner', b),

  // ── flywheel 1: test case metadata + performance ──────────────────────────
  patchTestCaseMetadata: (tsId, tcId, b) => patch(`/test-sets/${tsId}/cases/${tcId}/metadata`, b),
  getTestCasePerformance: (label, wid)   => get(`/test-case-performance/${encodeURIComponent(label)}`,
                                                 wid ? { workflow_id: wid } : {}),
  exportTestCaseCorpus: (wfId, params)   => `/api/workflows/${wfId}/test-case-corpus?${new URLSearchParams(params || {})}`,

  // ── flywheel 2: reviewer profiles ─────────────────────────────────────────
  getReviewerProfile:   (rid)            => get(`/reviewer-profile/${encodeURIComponent(rid)}`),
  upsertReviewerProfile:(rid, b)         => post(`/reviewer-profile/${encodeURIComponent(rid)}`, b),

  // ── flywheel 2: consent management ────────────────────────────────────────
  listConsents:         (wid)            => get('/consent', wid ? { workflow_id: wid } : {}),
  grantConsent:         (b)              => post('/consent', b),
  revokeConsent:        (id)             => del(`/consent/${id}`),

  // ── flywheel 2: preference corpus export ──────────────────────────────────
  exportPreferenceCorpus: (erId, params) => `/api/eval-runs/${erId}/export/preference-corpus?${new URLSearchParams(params || {})}`,
  exportGlobalPreferenceCorpus: (params) => `/api/preference-corpus?${new URLSearchParams(params || {})}`,

  // ── collaboration: comments ───────────────────────────────────────
  listComments:       (compId)          => get(`/comparisons/${compId}/comments`),
  addComment:         (compId, b)       => post(`/comparisons/${compId}/comments`, b),
  updateComment:      (commentId, b)    => patch(`/comments/${commentId}`, b),
  deleteComment:      (commentId)       => del(`/comments/${commentId}`),

  // ── collaboration: review assignments ─────────────────────────────
  assignReview:       (compId, b)       => post(`/comparisons/${compId}/assign`, b),
  bulkAssign:         (erId, b)         => post(`/eval-runs/${erId}/assign`, b),
  updateAssignment:   (aId, b)          => patch(`/assignments/${aId}`, b),
  listAssignments:    (q = {})          => get('/assignments', q),
  getReviewQueue:     (rid)             => get(`/review-queue/${encodeURIComponent(rid)}`),
  getReviewStats:     (erId)            => get(`/eval-runs/${erId}/review-stats`),

  // ── prompt playground ─────────────────────────────────────────────
  playgroundRun:      (b)              => post('/playground', b),

  // ── demo gallery ──────────────────────────────────────────────────
  listDemos:          ()               => get('/demos'),
  seedDemos:          (b)              => post('/demos/seed', b),
  resetDemos:         (b)              => fetch(`${BASE}/demos/reset`, {
                                            method: 'DELETE',
                                            headers: writeHeaders(),
                                            body: JSON.stringify(b),
                                          }).then(_json),

  // ── agent comparison (v0.1.2) ────────────────────────────────────
  agentFeatureStatus: ()               => get('/agent/feature-status'),
  agentTraceEvents:   (branchId)       => get('/agent/trace-events', { branch_id: branchId }),
  agentTrajectory:    (compId)         => get(`/agent/trajectory/${compId}`),
}
