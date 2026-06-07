# Provider Registry — Implementation Task List

**Feature:** Multi-provider LLM support with per-branch provider selection  
**Goal:** Allow users to configure multiple LLM providers and assign different providers to each comparison branch, enabling cross-provider A/B testing while maintaining backward compatibility and security.

---

## Design Principles

1. **Zero-config default** — The platform works identically to today when no providers are configured. The existing global `openai_api_key` setting continues to work as a fallback.
2. **Backward-compatible migration** — On first access, the existing API key auto-migrates into a "Default" provider entry. No user action required.
3. **Security-first** — All API keys encrypted at rest with Fernet (reusing existing encryption infrastructure). Keys are never returned in full from any API endpoint.
4. **Progressive disclosure** — Non-technical users see a simple provider list. Advanced users can assign per-branch providers in the workflow builder.
5. **Scorer stays global** — The divergence scorer (LLM-as-judge) continues to use the default provider. Only runner and playground branches get per-provider support.

---

## Task Dependency Graph

```
#17 Data Model & Migration
 └─► #18 Provider CRUD API
      ├─► #19 Runner & Playground Integration
      │    ├─► #22 Provider Selector in WorkflowBuilder & Playground
      │    ├─► #23 Provider Labels in Result Views
      │    └─► #24 Test Suite (also needs #20)
      └─► #20 API Client (api.js)
           └─► #21 Provider Management UI (Settings)
                └─► #22 Provider Selector (also needs #19)

#25 Final Verification & Docs (blocked by #21, #22, #23, #24)
```

---

## Tasks

### Task #17 — Design provider registry data model and migration
**Priority:** Critical | **Effort:** Medium | **Layer:** Database + Core

Create a `llm_providers` table:

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT (UUID) | Primary key |
| `name` | TEXT | User-facing label, e.g. "OpenAI Production", "Anthropic Dev" |
| `provider_type` | TEXT | `openai`, `anthropic`, `openrouter`, `ollama`, `custom` |
| `base_url` | TEXT | Nullable — defaults to provider-standard URL |
| `api_key_encrypted` | TEXT | Fernet-encrypted, same scheme as existing settings |
| `is_default` | BOOLEAN | Exactly one row should be `true` |
| `created_at` | TEXT (ISO) | |
| `updated_at` | TEXT (ISO) | |

Migration logic:
- On startup, if `llm_providers` table is empty and `openai_api_key` exists in settings, auto-create a "Default (migrated)" provider entry with that key.
- Add provider CRUD methods to `core/store.py`.

---

### Task #18 — Build provider CRUD API routes
**Priority:** Critical | **Effort:** Medium | **Layer:** Backend API  
**Blocked by:** #17

Create `backend/routes/providers.py` with endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/providers` | List all providers (keys masked) |
| `POST` | `/api/providers` | Create a new provider |
| `PATCH` | `/api/providers/{id}` | Update provider (skip key if blank) |
| `DELETE` | `/api/providers/{id}` | Delete provider (prevent deleting default if it's the only one) |
| `POST` | `/api/providers/{id}/test` | Test connection — makes a lightweight API call to verify credentials |

Response model masks API key to last 4 characters (`sk-...7x2f`). All endpoints require `X-API-Key` auth (same as existing write endpoints).

---

### Task #19 — Add provider_id to runner and playground branch configs
**Priority:** Critical | **Effort:** Medium | **Layer:** Backend Logic  
**Blocked by:** #18

- Add optional `provider_id: str | None` field to `RunnerBranchConfig` and `PlaygroundRequest`.
- Update `_call_llm()` in `backend/routes/runner.py` to resolve provider credentials:
  1. If `provider_id` is set → look up provider, decrypt key, use its base_url.
  2. If `provider_id` is null → use default provider.
  3. If no providers exist → fall back to global `openai_api_key` setting (full backward compat).
- Store `provider_id` in comparison metadata so results record which provider was used.
- Same logic for playground endpoint.

---

### Task #20 — Add provider methods to api.js client
**Priority:** High | **Effort:** Small | **Layer:** Frontend API  
**Blocked by:** #18

Add to the `api` object in `frontend/src/api.js`:

```javascript
// providers
listProviders:    ()          => authGet('/providers'),
createProvider:   b           => post('/providers', b),
updateProvider:   (id, b)     => patch(`/providers/${id}`, b),
deleteProvider:   id          => del(`/providers/${id}`),
testProvider:     id          => post(`/providers/${id}/test`, {}),
```

---

### Task #21 — Build provider management UI in Settings
**Priority:** High | **Effort:** Large | **Layer:** Frontend UI  
**Blocked by:** #20

Create `frontend/src/components/settings/ProviderSection.jsx`:

- Provider list: cards showing name, provider type icon, base URL, masked key, default badge.
- Add/Edit: inline expandable form (matching existing Settings card patterns).
- "Test Connection" button with loading spinner and success/error feedback.
- Delete with confirmation dialog.
- "Set as Default" action.
- Empty state: friendly message explaining what providers are and why you'd add one, with a single "Add Provider" CTA.
- Wire into `Settings.jsx` — render above or below existing LLM Configuration section.

---

### Task #22 — Add provider selector to WorkflowBuilder and Playground
**Priority:** High | **Effort:** Medium | **Layer:** Frontend UI  
**Blocked by:** #21, #19

- Add a provider dropdown to `BranchEditor` in `WorkflowBuilder.jsx`.
  - Shows "Default Provider (name)" as first option.
  - Lists all configured providers.
  - InfoTip: "Each branch can use a different LLM provider — useful for comparing OpenAI vs. Anthropic on the same prompts."
- Add the same dropdown to `Playground.jsx`.
- If zero non-default providers exist, hide the dropdown entirely (no UI clutter for simple setups).
- Selected `provider_id` is included in the runner/playground request payload.

---

### Task #23 — Show provider info in EvalRunDetail and comparison views
**Priority:** Medium | **Effort:** Small | **Layer:** Frontend UI  
**Blocked by:** #19

- In `EvalRunDetail.jsx`: show provider name badge next to each branch header when `provider_id` is present in the run config.
- In `BranchCompare.jsx`: same treatment — subtle label like "via OpenAI Production".
- No changes when `provider_id` is null (backward-compatible display).
- Provider name resolved from a lightweight lookup (cache the provider list).

---

### Task #24 — Comprehensive test suite for provider registry
**Priority:** High | **Effort:** Medium | **Layer:** Testing  
**Blocked by:** #19, #20

Test coverage:

1. **CRUD operations** — create, list, update, delete, set-default, prevent-delete-last-default.
2. **Key encryption** — Fernet roundtrip, masked response never contains raw key, key rotation.
3. **Test connection** — mock OpenAI client, verify success/failure paths.
4. **Per-branch resolution** — provider_id resolves to correct credentials, null falls back to default, missing provider returns clear error.
5. **Migration** — existing `openai_api_key` auto-migrates to default provider entry.
6. **Security** — all provider endpoints require API key auth, no key leakage in any response.
7. **Backward compatibility** — platform functions identically with zero providers configured.

---

### Task #25 — Final verification, documentation, and version notes
**Priority:** Critical | **Effort:** Medium | **Layer:** Cross-cutting  
**Blocked by:** #21, #22, #23, #24

- Run full backend test suite (target: 0 failures).
- Run frontend build (target: clean compile, 0 errors).
- Update `docs/docs/architecture.md` with provider registry section.
- Update API reference in MkDocs with provider endpoints.
- Add CHANGELOG entry for the provider registry feature.
- Smoke test the complete flow end-to-end:
  1. Add a provider via Settings UI.
  2. Assign it to Branch B in WorkflowBuilder.
  3. Run a comparison.
  4. Verify results display the correct provider labels.
- Verify zero-provider state equals current platform behavior (no regression).

---

## Estimated Total Effort

| Category | Tasks | Effort |
|----------|-------|--------|
| Database + Core | #17 | Medium |
| Backend API | #18, #19 | Medium + Medium |
| Frontend API | #20 | Small |
| Frontend UI | #21, #22, #23 | Large + Medium + Small |
| Testing | #24 | Medium |
| Verification | #25 | Medium |

**Critical path:** #17 → #18 → #19 → #22 → #25

The feature is designed to be fully backward-compatible. If a user never configures a provider, the platform behaves exactly as it does today — the global API key in Settings continues to work unchanged.
