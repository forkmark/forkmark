# Architecture

Forkmark is a self-hosted evaluation platform built as a Python backend with a React single-page application frontend. This page describes the major components, data flow, and design decisions that shape the system.

## System overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         React SPA (Vite)                            │
│  Dashboard · Eval Runs · Comparisons · Decisions · Export · Settings│
└────────────────────────────┬────────────────────────────────────────┘
                             │  REST API (JSON)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                            │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────────────┐  │
│  │ SDK      │  │ UI       │  │ Export    │  │ Background        │  │
│  │ Routes   │  │ Routes   │  │ Routes   │  │ Workers           │  │
│  │ (keyed)  │  │ (16 mods)│  │ (DPO,CSV)│  │ (scoring, eval)   │  │
│  └──────────┘  └──────────┘  └───────────┘  └───────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     Core Engine                               │   │
│  │  Store · Comparator · Evaluators · Divergence Scoring         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
                ┌─────────┐                  ┌────────────┐
                │ SQLite   │                  │ PostgreSQL │
                │ (dev)    │                  │ (prod)     │
                └─────────┘                  └────────────┘
```

## Data model

The core data model follows a strict hierarchy. Every entity is immutable once created, except for decisions which are the primary mutable state in the system.

```
TestSet
  └── TestCase (labeled input + expected output)
        └── EvalRun (a batch evaluation session)
              └── WorkflowRun (one test case executed)
                    ├── Branch A → StepOutput(s)
                    └── Branch B → StepOutput(s)
                          └── Comparison (auto-generated pair)
                                └── Decision (human verdict)
```

**TestSet** groups related test cases for consistent evaluation. Each **TestCase** carries a label, input data, and optional expected output or tags for filtering.

**EvalRun** represents a single evaluation session — comparing Branch A config vs Branch B config across a set of test cases. It tracks progress, branch configurations, and aggregated statistics.

**WorkflowRun** captures one execution of the workflow under test. The SDK creates two branches per run, each producing **StepOutput** records for every step in the workflow pipeline.

**Comparison** is the atomic unit of evaluation. The system automatically pairs Branch A and B outputs from the same workflow run, computes divergence scores, and presents them for human review.

**Decision** records the human verdict: which branch won (A, B, neither, or both), a confidence level (high, medium, low), a rationale for the choice, and a rationale for rejection. This structured format is what makes Forkmark's DPO export possible.

## Backend architecture

### Route modules

The FastAPI application is split into 16 route modules under `backend/routes/`:

| Module | Responsibility |
|--------|---------------|
| `sdk.py` | SDK ingestion endpoints (API key authenticated) |
| `eval_runs.py` | Eval run CRUD and lifecycle |
| `test_sets.py` | Test set and test case management |
| `workflows.py` | Workflow listing and run history |
| `comparisons.py` | Comparison browsing and scoring |
| `decisions.py` | Decision recording and export (DPO, CSV, JSONL) |
| `keys.py` | API key management |
| `settings.py` | Application settings and reviewer profiles |
| `collaboration.py` | Comments and review assignments |
| `exports.py` | Preference corpus export |
| `stats.py` | Dashboard statistics and charts |
| `runner.py` | No-code workflow runner and playground |
| `providers.py` | LLM provider registry CRUD and connection testing |
| `demos.py` | Demo gallery seeding |
| `admin.py` | Maintenance and pruning |
| `health.py` | Liveness and readiness probes |

Shared dependencies — database instance, authentication, caching, rate limiting — live in `backend/deps.py` so every route module stays focused on its own concern.

### Divergence scoring

Every comparison receives an automatic divergence score through a configurable pipeline:

1. **Lexical** — Character-level edit distance, normalized to 0-1. Fast baseline for detecting any textual change.
2. **Semantic** — Sentence-transformer cosine similarity. Catches paraphrases that lexical scoring misses.
3. **OpenAI embeddings** — Uses `text-embedding-3-small` (or configured model) for higher-quality semantic comparison.
4. **LLM-as-judge** — Sends both outputs to a judge model with a structured rubric. Most expensive but catches nuanced quality differences.

The `auto` mode (default) picks the best available scorer based on what's configured — falling back gracefully from LLM judge to semantic to lexical.

### Provider registry

Forkmark supports multiple LLM providers through a built-in registry stored in the `llm_providers` table. Each provider entry holds a name, type (openai, anthropic, openrouter, ollama, or custom), base URL, and an API key encrypted with Fernet symmetric encryption using the `FM_SECRET_KEY` environment variable.

Credential resolution follows a three-tier fallback:

1. **Explicit provider** — If a branch specifies a `provider_id`, those credentials are used directly.
2. **Default provider** — If no explicit provider is set, the provider marked `is_default` is used.
3. **Legacy settings** — If no providers exist in the registry, the system falls back to the `openai_api_key` setting or `OPENAI_API_KEY` environment variable.

This design ensures zero-config backward compatibility: existing deployments that use a single API key in settings continue to work without any changes. When a user first visits the Providers settings page, any existing legacy key is automatically migrated into a "Default (migrated)" provider entry.

The runner and playground support per-branch provider selection, allowing users to compare outputs from different LLM providers in a single eval run. The divergence scorer always uses the default provider to keep scoring consistent across branches.

### Authentication

Two authentication layers operate independently:

- **SDK authentication** — API keys (prefixed `fm_`) authenticate SDK write operations. Keys are hashed with SHA-256 before storage.
- **UI authentication** — Optional, controlled by `FM_REQUIRE_UI_AUTH`. When enabled, UI write operations require a valid API key sent as `X-API-Key`. Read operations are unauthenticated by default.

### Background workers

A configurable thread pool (1-16 workers via `FM_BACKGROUND_WORKERS`) processes divergence scoring and evaluation tasks asynchronously. This keeps API response times low while heavy computation happens in the background.

## Frontend architecture

The frontend is a React single-page application built with Vite. It uses hash-based routing (`#view?param=value`) for simplicity — no server-side routing configuration needed.

Key design decisions:

- **No component library** — All components are custom-built with inline styles and CSS variables for theming. This keeps the bundle small and avoids version conflicts.
- **Lazy loading** — Every view is loaded via `React.lazy()` so the initial bundle stays under 100KB.
- **Session storage for keys** — API keys are stored in `sessionStorage` (cleared on tab close) rather than `localStorage` to reduce XSS exposure.
- **CSS variable theming** — Dark and light themes are implemented via CSS custom properties, switchable without page reload.

## Storage backends

Forkmark supports two storage backends:

- **SQLite** (default) — Zero-config, single-file database. Suitable for local development and small-to-medium deployments. Uses WAL mode for concurrent read/write.
- **PostgreSQL** — Production-grade. Recommended for teams and required for multi-tenant deployments. Enabled by setting the `FM_DATABASE_URL` environment variable.

All three backends share the same `Store` interface in `core/store.py`, so switching requires only a config change and restart.

## Enterprise features

Enterprise features are gated behind `FM_ENTERPRISE_MODE=true` and include:

- **Multi-tenancy** — Full tenant isolation with per-tenant PostgreSQL schemas
- **SCIM 2.0** — Automated user provisioning from identity providers
- **Device flow authentication** — OAuth device flow for CLI and headless environments
- **OpenTelemetry** — Distributed tracing export for observability platforms
- **Data residency** — Region-aware data routing for compliance requirements

When enterprise mode is disabled (the default), these modules are not loaded, keeping the community edition lightweight and simple.

## Deployment

Forkmark runs as a single Python process serving both the API and the SPA static files. In production, the recommended setup is:

```
                    ┌───────────┐
                    │  Reverse  │
                    │  Proxy    │
                    │ (nginx)   │
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ Forkmark │
                    │  (uvicorn)│
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ PostgreSQL│
                    └───────────┘
```

The application entry point is `run.py`, which launches the FastAPI app with uvicorn. The React frontend ships pre-built in `frontend/dist` (served as static files), and the database schema is created automatically on first start, so no build or migration step is required to run it. See the [deployment guide](deployment/self-hosted.md) for production configuration details.
