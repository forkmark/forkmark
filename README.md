# Forkmark

**Self-hosted A/B prompt comparison with human review and DPO export.**

Compare two LLM branches side-by-side, collect human preference decisions, and export training data for fine-tuning --- all without sending a single byte to the cloud.

[![CI](https://github.com/YOUR_ORG/forkmark/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/forkmark/actions)

---

## Quick Start

```bash
git clone https://github.com/YOUR_ORG/forkmark.git
cd forkmark
pip install -r requirements.txt
python run.py
```

Open **http://localhost:7700** --- click **Load Demo Data** to see it in action.

## What Forkmark Does

Forkmark is an evaluation platform for teams that need to compare LLM outputs and build preference datasets. The core workflow is:

1. **Send prompts to two model branches** via the Python SDK or the built-in Playground.
2. **Review outputs side-by-side** with inline diffs, divergence scoring, and cost breakdowns.
3. **Record human preference decisions** with rationale, confidence, and tags.
4. **Export DPO/RLHF training data** in one click --- ready for fine-tuning.

## Why Forkmark

| | Forkmark | Cloud Eval Tools |
|---|---|---|
| **Deployment** | Self-hosted, zero cloud dependency | Cloud-first, data leaves your network |
| **Core Workflow** | Human-in-the-loop A/B review as the *primary* UX | Evaluation is one feature among many |
| **Training Export** | DPO/RLHF export from review decisions | Stops at evaluation metrics |
| **Divergence Scoring** | Tiered: lexical, semantic, OpenAI embeddings, LLM-judge | Basic similarity only |
| **Cost** | Free, open source | Per-seat or usage-based pricing |

## SDK Integration

Already have outputs from your own pipeline? Log a comparison in a few lines:

```python
import forkmark

forkmark.init(api_key="fm_...", base_url="http://localhost:7700")

prompt = "Summarize this contract clause..."

with forkmark.run("contract-summary", input_data={"clause": prompt}) as run:
    run.log_step_output("summarise",
                        messages=[{"role": "user", "content": prompt}],
                        output=response_a, model="gpt-4o",            branch="A")
    run.log_step_output("summarise",
                        messages=[{"role": "user", "content": prompt}],
                        output=response_b, model="claude-3.5-sonnet", branch="B")
```

Forkmark scores the divergence and creates the comparison automatically. Open the UI to review, decide, and export.

Want Forkmark to call both models for a whole test set? Use `forkmark.eval_run(...)` with `case.step()` / `case.branch_step()` — see the [SDK docs](docs/docs/sdk/overview.md).

## Features

**Evaluation**: divergence scoring (4 tiers), inline diffs, cost tracking, background auto-scoring.
**Review**: keyboard-driven decisions (A/B/N shortcuts), confidence levels, tagging taxonomy, threaded comments.
**Export**: DPO JSONL, OpenAI fine-tuning format, decisions JSONL, CSV --- all one-click from the UI.
**Demos**: 9 industry demo scenarios pre-loaded --- healthcare, legal, finance, retail, and more.
**API**: Full REST API with OpenAPI docs at `/docs`. Python SDK included.

## Architecture

Forkmark is a single Python process (FastAPI) serving both the API and the React frontend. SQLite by default, PostgreSQL for production. No external services required.

```
Browser  --->  FastAPI (port 7700)  --->  SQLite / PostgreSQL
                  |
                  +-- React SPA (served from /frontend/dist)
                  +-- Background scoring (thread pool)
                  +-- LiteLLM price sync (startup)
```

## Configuration

All settings via environment variables. See `.env.example` for the full list.

| Variable | Default | Description |
|---|---|---|
| `FM_PORT` | `7700` | Server port |
| `FM_DATABASE_URL` | (SQLite) | PostgreSQL URL for production |
| `FM_DIVERGENCE_SCORER` | `auto` | `lexical`, `semantic`, `openai`, or `llm_judge` |
| `FM_OPENAI_API_KEY` | | Required for Playground and `openai`/`llm_judge` scorers |
| `FM_REQUIRE_UI_AUTH` | auto | Require an API key for UI endpoints (see security note) |
| `FM_SECRET_KEY` | | Enables Fernet encryption-at-rest for stored provider API keys |

> **Security note.** Bound to `127.0.0.1`/`localhost` (the default), the UI and its
> data exports are open for frictionless local use. Bound to any other interface
> (e.g. `0.0.0.0` on a server), Forkmark **requires an API key for all UI endpoints
> by default** so your preference/DPO data isn't exposed to the network. Set
> `FM_REQUIRE_UI_AUTH=true|false` to override, and set `FM_SECRET_KEY` to encrypt
> stored provider keys at rest.

## Development

```bash
# Backend
pip install -r requirements.txt
python run.py

# Frontend (hot reload)
cd frontend && npm install && npm run dev

# Tests
pytest tests/
```

## License

MIT
