# API Endpoints

All endpoints are prefixed with `/api/`. The `/api/v1/` prefix is also supported as an alias.

## Authentication

Most endpoints require an API key via the `X-API-Key` header. SDK endpoints always require it. UI read endpoints may be unauthenticated in single-tenant mode (controlled by `FM_REQUIRE_UI_AUTH`).

See [Authentication](authentication.md) for details.

## SDK endpoints

These are used by the Forkmark SDK and always require API key authentication.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/sdk/eval-runs` | Create an eval run |
| POST | `/api/sdk/eval-runs/{id}/complete` | Mark eval run as completed |
| POST | `/api/sdk/runs` | Create a workflow run |
| POST | `/api/sdk/runs/{id}/complete` | Complete a workflow run |
| POST | `/api/sdk/branches` | Create a branch |
| POST | `/api/sdk/steps` | Log a step output |
| POST | `/api/sdk/steps/batch` | Log step outputs in bulk |
| POST | `/api/sdk/comparisons` | Create a comparison |

## Workflows

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workflows` | List all workflows |
| GET | `/api/workflows/{id}` | Get workflow details |
| POST | `/api/workflows` | Create a workflow |
| DELETE | `/api/workflows/{id}` | Delete a workflow |
| GET | `/api/workflows/{id}/runs` | List runs for a workflow |

## Eval runs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/eval-runs` | List eval runs (filter by `workflow_id`) |
| POST | `/api/eval-runs` | Create an eval run |
| GET | `/api/eval-runs/{id}` | Get eval run details |
| DELETE | `/api/eval-runs/{id}` | Delete an eval run |
| PATCH | `/api/eval-runs/{id}/complete` | Mark eval run complete |
| GET | `/api/eval-runs/{id}/export` | Export decisions as JSONL |

## Test sets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/test-sets` | List test sets |
| POST | `/api/test-sets` | Create a test set |
| GET | `/api/test-sets/{id}` | Get test set with cases |
| DELETE | `/api/test-sets/{id}` | Delete a test set |
| POST | `/api/test-sets/{id}/cases` | Add a test case |
| POST | `/api/test-sets/{id}/cases/bulk` | Add cases in bulk |
| DELETE | `/api/test-sets/{id}/cases/{case_id}` | Remove a test case |
| POST | `/api/test-sets/{id}/version` | Create new version from frozen set |
| PATCH | `/api/test-sets/{id}/cases/{case_id}/metadata` | Update case metadata |

## Comparisons and decisions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/comparisons` | List comparisons (filter by `eval_run_id`) |
| GET | `/api/comparisons/{id}` | Get comparison with branches and steps |
| GET | `/api/comparisons/{id}/score-status` | Check scoring status |
| POST | `/api/comparisons/{id}/decide` | Record a decision |
| PATCH | `/api/comparisons/{id}/decide` | Update an existing decision |
| GET | `/api/decisions` | List decisions |

## Exports

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/decisions/export` | Export decisions as JSONL |
| GET | `/api/decisions/export/dpo` | Export as DPO training data |
| GET | `/api/decisions/export/openai-ft` | Export as OpenAI fine-tuning format |
| GET | `/api/preference-corpus` | Export enriched preference corpus |
| GET | `/api/eval-runs/{id}/export/preference-corpus` | Export preference corpus for eval run |

See [Export formats](exports.md) for details.

## API keys

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/keys` | List API keys |
| POST | `/api/keys` | Create an API key |
| DELETE | `/api/keys/{id}` | Revoke an API key |

## Settings

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Get all settings |
| PATCH | `/api/settings` | Update settings |

## Data consent

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/consent` | List consent records |
| POST | `/api/consent` | Grant consent |
| DELETE | `/api/consent/{id}` | Revoke consent |

## Flywheel

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/test-case-performance/{label}` | Get performance stats for a test case |
| GET | `/api/workflows/{id}/test-case-corpus` | Export test case corpus |
| GET | `/api/reviewer-profile/{id}` | Get reviewer profile |
| POST | `/api/reviewer-profile/{id}` | Update reviewer profile |

## Operations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/costs` | Cost breakdown |
| GET | `/api/tags` | List all tags |
| GET | `/metrics` | Prometheus-compatible metrics |
| DELETE | `/api/admin/prune` | Prune old step outputs |
| POST | `/api/runner` | Run an LLM call (for UI) |

## Rate limiting

All endpoints are rate-limited at 1000 requests per minute per API key (or per client IP for unauthenticated endpoints). Rate limiting uses Redis sorted sets when available, with a local in-memory fallback.

When rate-limited, endpoints return `429 Too Many Requests`.
