# Changelog

All notable changes to Forkmark are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Langfuse importer** — `forkmark import langfuse` turns generations already
  logged in Langfuse into Forkmark A/B comparisons by pairing the same input run
  through two models. Reads from a Langfuse export file (`--file`) or live from
  the Langfuse public API (`--from-api`, works with self-hosted Langfuse).
  Models are auto-detected or set with `--model-a`/`--model-b`; `--dry-run`
  previews without pushing. Available as the `forkmark` CLI and `python -m forkmark`.
- **Sample datasets** — `examples/langfuse_sample_export.json` (try the importer
  with no Langfuse account) and `examples/sample_dpo.jsonl` (the DPO export format).
- **Project files** — `LICENSE` (MIT), `CONTRIBUTING.md`, GitHub issue templates,
  and a pull-request template.

### Fixed

- **Workflow Builder crash** — the "Run Comparison" view threw
  `r.toLowerCase is not a function` because the `Input`/`Textarea` components
  derived their DOM id from `label.toLowerCase()`, but several fields pass a JSX
  element (with an `InfoTip`) as the label. Now guarded with a `useId()` fallback
  so JSX labels work and accessibility (label association) is preserved.
- Defensively hardened `modelCostPer1M()` against non-string model ids.
- `sdk/setup.py` declared the Apache license while the project is MIT; corrected
  the license classifier to match.

## [0.1.2] - 2026-06-07

First public open-source release. This version focuses on the LLM A/B comparison
→ human review → DPO export workflow, and hardens the project for launch.

### Added

- **Agent / trajectory comparison** — compare agent runs by tool-call sequence,
  reasoning, and outcome (`core/trajectory_comparator.py`, `core/agent_models.py`,
  `sdk/forkmark/agent.py`, Trajectory Compare UI). Shipped **disabled by default**
  (`FM_ENABLE_AGENT_COMPARISON=false`) while the feature matures; enable it to try it.
- **Host-aware authentication** — UI read/write endpoints (including data exports)
  now require an `X-API-Key` automatically when Forkmark is bound to a non-loopback
  interface, while staying open for frictionless local use on `127.0.0.1`. Override
  with `FM_REQUIRE_UI_AUTH`.
- **README quickstart regression test** (`tests/test_readme_example.py`) that keeps
  the documented SDK snippet in sync with the real SDK surface.

### Changed

- **Single canonical quickstart** — the README is now the one getting-started path
  (simple single-process / SQLite / port 7700). Production deployment (PostgreSQL,
  Redis, TLS, first-key bootstrap) is consolidated into
  `docs/deployment/self-hosted.md`.
- **Corrected the SDK quickstart** to the supported API
  (`forkmark.init()` / `forkmark.run()` / `log_step_output()`).
- **`.env.example` clarified** — `FM_SECRET_KEY` documented as the
  encryption-at-rest key for stored provider credentials; authentication behavior
  documented.

### Removed

- **`USER_GUIDE.md`** — contradicted the README (described a different deploy model
  and an out-of-date SDK API); its production content now lives in the self-hosted
  deployment guide.
- **`backend/main_monolith.py`** — dead pre-refactor monolith (~2,254 lines).
- **Stale frontend build artifacts** (`frontend/dist_v2`–`dist_v5`).

### Security

- Preference/DPO export endpoints are no longer reachable without an API key on
  networked deployments (see Host-aware authentication above).

### Deferred

- **Enterprise stack initialization is a no-op in this OSS build.** Multi-tenancy,
  SCIM, device-flow, and data-residency modules are not shipped here; they will
  return as license-gated `ee/` features in a future release.

### Fixed

- Headline SDK example previously referenced a nonexistent `run.compare()` and the
  wrong `ForkmarkClient(...)` argument order, so the documented quickstart could
  not run as written.

## [0.1.1] - 2026-05-26

### Added

- **Multi-provider registry** — Full CRUD management for LLM providers (OpenAI, Anthropic, OpenRouter, Ollama, custom). API keys are Fernet-encrypted at rest with masked display in the UI. Supports per-branch provider selection in both the workflow runner and prompt playground.
- **Provider connection testing** — One-click connection test for each provider, with latency measurement and detailed error messages. Supports both OpenAI-compatible (`/models`) and Anthropic (`/messages`) API formats.
- **Legacy key auto-migration** — Existing `openai_api_key` settings are automatically migrated into a "Default (migrated)" provider entry on first access. Provider type is auto-detected from the base URL.
- **Per-branch credential resolution** — Runner and playground resolve credentials independently per branch: explicit provider → default provider → legacy settings fallback. Divergence scorer uses the default provider.
- **Provider management UI** — New "LLM Providers" section in Settings with add/edit forms, masked key display, default provider badge, test connection button, and delete confirmation. Progressive disclosure hides provider dropdowns when only one provider is configured.
- **DPO Export UI** — Prominent "Export DPO" button on Eval Run detail and Decision History pages with gradient styling and dropdown menu for all export formats (JSONL, CSV, DPO, OpenAI fine-tuning, preference corpus).
- **CSV export** — New CSV export format for decisions alongside existing JSONL.
- **Architecture documentation** — Comprehensive architecture page covering data model, backend modules, divergence scoring pipeline, storage backends, and deployment topology.
- **"Why Forkmark" page** — Product positioning document explaining the comparison-first approach, DPO flywheel, and differentiation from logging-first platforms.
- **MkDocs deployment** — GitHub Actions workflow for automatic documentation deployment to GitHub Pages on push to main.
- **Response models** — Pydantic response models for all 62 API endpoints with OpenAPI schema generation (44 schemas).
- **Enterprise mode gating** — `FM_ENTERPRISE_MODE` environment variable controls loading of enterprise modules (multi-tenancy, SCIM, device flow, data residency). Community edition runs without enterprise overhead by default.
- **Community/Enterprise edition indicator** — Sidebar footer and Settings page show current edition. Enterprise-only nav items (Review Queue, Observability) are hidden in community mode.
- **Health endpoints** — Dedicated liveness and readiness probe routes for container orchestration.

### Changed

- **Backend modularization** — Refactored monolithic `main.py` (2,254 lines) into 16 focused route modules under `backend/routes/` with shared dependencies in `backend/deps.py`. All API routes preserved.
- **Schema migration v7** — Added `llm_providers` table and `provider_id` column on `branches` for provider-aware eval runs.
- **Runner credential flow** — `_resolve_credentials()` now supports three-tier fallback: explicit provider_id → default provider → legacy settings/env vars.
- **Version bumped** to 0.1.1 in sidebar and configuration.

### Fixed

- Missing `Query` import in settings route module.
- Enterprise modules no longer load unconditionally — gated behind explicit opt-in flag.

## [0.1.0] - 2026-05-12

### Added

- Initial release of Forkmark.
- SDK for Python workflow instrumentation.
- Pairwise A/B comparison with four-tier divergence scoring (lexical, semantic, OpenAI embeddings, LLM-as-judge).
- Structured decision recording with choice, confidence, and rationale.
- DPO and OpenAI fine-tuning export from preference data.
- Consent-gated preference corpus with reviewer profiles.
- No-code workflow runner and prompt playground.
- Demo gallery with one-click seed data.
- Multi-tenant PostgreSQL support with SCIM 2.0 provisioning.
- SQLite, DuckDB, and PostgreSQL storage backends.
- Dark/light theme with fully responsive UI.
- API key authentication for SDK operations.
- Review queue with assignment and collaboration features.
- OpenTelemetry integration for distributed tracing.
