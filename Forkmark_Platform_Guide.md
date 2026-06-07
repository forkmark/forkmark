# Forkmark Platform Guide (v0.1.2)

> *From "What is this?" to "How does it work under the hood?" — a progressive deep-dive.*

---

## Part 1 — The Big Picture (Non-Technical)

### What is Forkmark?

Imagine you run a restaurant and you're testing two new recipes for your signature dish. You wouldn't just guess which one is better — you'd have customers taste both, side by side, and tell you which they prefer. After enough taste tests, you'd have real data to pick the winner.

**Forkmark does exactly this, but for AI.**

When a company builds a product that uses AI (a chatbot, a document summarizer, a code assistant), they face a critical question: *"Is our AI actually giving good answers?"* And when they consider switching to a newer AI model or tweaking their instructions, they face another: *"Will this change make things better or worse?"*

Today, most teams answer these questions with gut feelings — what the industry calls **"vibes-based evaluation."** Someone reads a few AI responses, thinks "yeah, that looks good," and ships it.

Forkmark replaces vibes with evidence. It lets you:

1. **Show the same question to two different AI setups** (different models, different instructions, different settings)
2. **Display both answers side by side** so a human reviewer can compare them
3. **Record which answer was better** — and why
4. **Use those preferences to make the AI better** (by exporting training data)

> **Key insight:** Forkmark doesn't host or run AI models itself. It's the testing lab, not the kitchen. You bring your own AI (OpenAI, Anthropic, Google, or local models), and Forkmark provides the framework to systematically compare and evaluate their outputs.

### Why does this matter?

| Without Forkmark | With Forkmark |
|---|---|
| "I read 5 responses, they seemed fine" | "We tested 200 prompts across 2 models, Model B won 64% of the time with high confidence" |
| No record of why you chose a model | Every decision has a rationale, confidence level, and tags |
| Switching models is a leap of faith | A/B test the switch before committing |
| Training data for improving AI is scattered | One-click export of human preferences in standard fine-tuning formats |
| Evaluation is a one-time event | Evaluation is a continuous, repeatable process |

### Who is it for?

- **AI Engineers** — rigorously A/B test prompt changes and model upgrades before shipping to production
- **ML Teams** — build evaluation pipelines and generate DPO/RLHF training data for fine-tuning models
- **Quality & Annotation Teams** — conduct human evaluations at scale with reviewer assignments, review queues, and inter-annotator analysis
- **Research Groups** — run pairwise preference studies with built-in consent management for ethical data collection

---

## Part 2 — The Core Workflow (Beginner-Friendly)

Forkmark's workflow is built around a simple loop: **Compare → Decide → Learn**. Let's walk through it step by step.

### Step 1: Set Up Two "Branches"

A **branch** is one configuration of an AI system. Think of it like a contestant in a competition. You always have exactly two:

- **Branch A (Baseline)** — your current setup (e.g., GPT-4o with your existing prompt)
- **Branch B (Challenger)** — the thing you want to test (e.g., Claude 3.5 with a revised prompt)

```
           Same question
               │
       ┌───────┴────────┐
       ▼                 ▼
   Branch A           Branch B
  (Baseline)        (Challenger)
   GPT-4o            Claude 3.5
  "You are a         "You are a senior
   helpful            engineer. Always
   assistant."        include type hints."
       │                 │
       ▼                 ▼
   Response A         Response B
```

### Step 2: Send Test Cases

A **test case** is a question or prompt you want both branches to answer. You can have one, ten, or thousands.

**Example test cases for a customer support chatbot:**

| # | Test Case | Domain |
|---|---|---|
| 1 | "I want to return my order" | Returns |
| 2 | "My package hasn't arrived" | Shipping |
| 3 | "Can I get a discount?" | Pricing |
| 4 | "Your product broke after one day" | Complaints |

Both branches receive the same test cases, ensuring a fair comparison.

### Step 3: Review Side by Side

Forkmark shows you both responses next to each other, with differences highlighted (like "Track Changes" in Word). It also automatically calculates a **divergence score** — a number from 0 to 1 that tells you how different the two responses are:

- **0.0** — Identical (both said the same thing)
- **0.3** — Minor differences (same meaning, different wording)
- **0.7** — Significant differences (different approaches or content)
- **1.0** — Completely different

### Step 4: Make a Decision

For each pair of responses, a reviewer picks:

| Choice | Meaning |
|---|---|
| **Branch A** | The baseline was better |
| **Branch B** | The challenger was better |
| **Tie** | Both were equally good |
| **Skip** | Can't decide / not applicable |

Each decision also captures:
- **Confidence** — high, medium, low, or definitive
- **Rationale** — a free-text explanation of *why*
- **Tags** — categories like "tone," "accuracy," "completeness"

### Step 5: Export and Learn

Once you've collected enough decisions, Forkmark exports them in formats that AI models can learn from:

- **DPO format** — "Here's a prompt, here's a good answer, here's a bad answer"
- **OpenAI fine-tuning format** — ready to upload to OpenAI for model training
- **CSV / JSONL** — for custom analysis

This closes the loop: your human judgments become training data that makes the AI better.

> **Analogy:** Forkmark is like a science fair judging system. Students (AI models) submit projects (responses). Judges (reviewers) compare projects in pairs, score them, write feedback, and declare winners. The results are then compiled into a report that helps future students (fine-tuned models) do better.

---

## Part 3 — What Can You Do With Forkmark? (Use Cases with Examples)

### Use Case 1: Model Migration ("Should we switch from GPT-4 to Claude?")

Your company has been using GPT-4o for six months. Anthropic released Claude 3.5, and you're curious if it's better for your use case.

1. **Collect 100 real prompts** from your production logs
2. **Create a Test Set** in Forkmark with these prompts
3. **Run an Eval Run**: Branch A = GPT-4o, Branch B = Claude 3.5
4. **Have 3 reviewers** each review all 100 comparisons
5. **Check the dashboard**: Claude won 62% of the time, GPT-4o won 28%, 10% were ties
6. **Export the decisions** and present to leadership with confidence

**Time saved:** Instead of weeks of ad-hoc testing, you have statistically meaningful results in a day.

### Use Case 2: Prompt Engineering ("Is my new system prompt better?")

You've rewritten the system prompt for your coding assistant. Does the new version produce better code?

```
Branch A (Baseline):
  "You are a helpful coding assistant."

Branch B (Challenger):
  "You are a senior Python engineer. Follow PEP 8.
   Always include docstrings and type hints.
   Prefer readability over cleverness."
```

Run 50 coding questions through both. The detailed prompt wins on code quality but uses 40% more tokens (= higher cost). Now you have data to make a cost-quality tradeoff decision.

### Use Case 3: RAG Pipeline Evaluation ("Are our retrieved documents relevant?")

You've built a Retrieval-Augmented Generation (RAG) system — an AI that answers questions using your company's internal documents. You want to check:

- **Faithfulness** — Is the AI sticking to what the documents say, or hallucinating?
- **Relevance** — Is the AI actually answering the question asked?

Forkmark's built-in evaluators can automatically score these dimensions using LLM-as-judge techniques, even before a human reviews them.

### Use Case 4: Agent Comparison ("Which AI agent is better at research?")

*(New in v0.1.2)*

Modern AI systems aren't just answering questions — they're executing multi-step workflows: browsing the web, calling APIs, running code. Forkmark can now compare **agent trajectories** — the entire sequence of decisions and actions an agent takes.

```
Agent A Trajectory:                 Agent B Trajectory:
1. 🧠 Reasoning: plan search       1. 🧠 Reasoning: plan search
2. 🔧 Tool: google_search          2. 🔧 Tool: web_browse
3. 📄 Result: 5 articles           3. 📄 Result: 3 articles
4. 🧠 Reasoning: synthesize        4. 🔧 Tool: google_search
5. 📝 Final answer                 5. 📄 Result: 4 articles
                                   6. 🧠 Reasoning: cross-reference
                                   7. 📝 Final answer
```

Forkmark scores trajectories on three dimensions:
- **Tool sequence alignment** — Did both agents use similar tools in similar order?
- **Outcome equivalence** — Did they arrive at the same final answer?
- **Efficiency** — Which one was faster, cheaper, and used fewer steps?

### Use Case 5: Building Training Data ("The DPO Flywheel")

Every time a reviewer picks "Branch B is better," that creates a training example:

```json
{
  "prompt": "How do I reset my password?",
  "chosen": "Go to Settings > Security > Reset Password...",
  "rejected": "You can change your password in the settings area."
}
```

Export hundreds of these, fine-tune your model, deploy the improved version as the new baseline, and run the comparison again. This creates a **flywheel** where your AI gets better with every evaluation cycle.

---

## Part 4 — Architecture Overview (Intermediate)

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser (React SPA)                     │
│   Dashboard • Workflow Builder • Playground • Branch Compare │
│   Agent Trajectory View • Decision History • Demo Gallery    │
└───────────────────────────┬─────────────────────────────────┘
                            │  REST API (HTTP)
┌───────────────────────────▼─────────────────────────────────┐
│                   FastAPI Backend (port 7700)                 │
│   16 route modules • 62 endpoints • Pydantic response models │
│   Auth (API key / JWT / CI token) • Rate limiting (1000/min) │
│   LiteLLM price sync • Background scoring pool               │
├──────────────────────┬──────────────────────────────────────┤
│   Core Engine        │   Infrastructure                      │
│   ├─ models.py       │   ├─ message_bus.py (Redis Streams)   │
│   ├─ store.py        │   ├─ workspace_router.py (tenancy)    │
│   ├─ comparator.py   │   ├─ auth_middleware.py (RBAC)        │
│   ├─ evaluators.py   │   ├─ audit.py (enterprise logging)    │
│   └─ trajectory_     │   ├─ observability.py (OTel + metrics)│
│      comparator.py   │   └─ feature_flags.py (gating)        │
└──────────────────────┴──────────┬───────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
  ┌──────────────┐    ┌────────────────────┐    ┌──────────────┐
  │   Database    │    │   Redis (optional)  │    │ AI Providers  │
  │  SQLite (dev) │    │  Caching, rate      │    │ OpenAI        │
  │  PostgreSQL   │    │  limiting, message  │    │ Anthropic     │
  │  (prod)       │    │  bus, Celery broker │    │ Google        │
  └──────────────┘    └────────────────────┘    │ Ollama        │
                                                │ OpenRouter    │
                                                │ Custom        │
                                                └──────────────┘
```

### Data Model Hierarchy

The data flows through a strict hierarchy:

```
TestSet                         ─── Reusable collection of test inputs (versioned, freezable)
  └── TestCase                  ─── One input with optional domain/industry metadata
        └── EvalRun             ─── Batch evaluation: N test cases × 2 branch configs
              └── WorkflowRun   ─── One execution per test case
                    ├── Branch A (baseline)     ─── Configuration + results for variant A
                    │     └── StepOutput        ─── One LLM call result (text, tokens, latency)
                    ├── Branch B (challenger)   ─── Configuration + results for variant B
                    │     └── StepOutput
                    ├── Comparison              ─── Side-by-side with divergence_score + eval results
                    │     └── Decision          ─── Human verdict (A/B/tie/skip, confidence, rationale)
                    └── TrajectoryOutcome       ─── Agent-level scoring (new in v0.1.2)
```

**Important:** Forkmark is **SDK-driven** — it does not execute LLM calls itself. Your code (or the built-in Playground) calls the AI provider, and then sends the results to Forkmark for storage and comparison. This keeps Forkmark lightweight and provider-agnostic.

### Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | React 18.3 + Vite 5.3 | Hash-based routing, lazy-loaded views, CSS variables, Recharts for charts |
| **Backend** | Python + FastAPI | Async, Pydantic validation, 16 route modules |
| **Database** | SQLite / PostgreSQL | SQLite for dev, PostgreSQL for production |
| **Caching** | Redis (optional) | Inline diff cache (24h TTL), rate limiting, message bus |
| **Background** | Thread pool or Celery | Async divergence scoring (1–16 configurable workers) |
| **Auth** | API keys (Argon2id) + JWT + CI tokens | Multi-tenant RBAC with 5 roles and 12 permissions |
| **Observability** | OpenTelemetry + Prometheus metrics | Structured JSON logging, p50/p95/p99 histograms |

---

## Part 5 — Divergence Scoring Deep Dive (Intermediate–Advanced)

The divergence score is the heart of Forkmark's comparison engine. It quantifies *how different* two AI responses are. Forkmark offers **four scoring tiers**, each trading speed for accuracy:

### Tier 1: Lexical (~1ms, free)

**How it works:** Combines TF-IDF cosine similarity (70% weight) with SequenceMatcher (30% weight) on the raw text.

**Good for:** Quick filtering — rapidly identifying which comparisons have big differences vs. negligible ones.

**Example:**
```
Response A: "The capital of France is Paris."
Response B: "Paris is the capital city of France."

Lexical divergence: 0.15  (very similar — same words, different order)
```

### Tier 2: Semantic (~50ms, free)

**How it works:** Uses the `all-MiniLM-L6-v2` sentence-transformer model to embed both responses into 384-dimensional vectors, then computes cosine similarity.

**Good for:** Production use — catches paraphrases that lexical matching would miss.

**Example:**
```
Response A: "The capital of France is Paris."
Response B: "France's seat of government is located in Paris."

Lexical divergence: 0.45  (many different words)
Semantic divergence: 0.08  (almost identical meaning)
```

### Tier 3: OpenAI Embeddings (~200ms, ~$0.0001/pair)

**How it works:** Uses OpenAI's `text-embedding-3-small` model for even richer semantic understanding.

**Good for:** When you need commercial-grade embeddings for nuanced text comparison.

### Tier 4: LLM-as-Judge (2–5s, ~$0.001/pair)

**How it works:** Sends both responses to a judge model (default: `gpt-4o-mini`) with a structured prompt asking it to evaluate differences on multiple dimensions. Returns both a score and a human-readable summary.

**Good for:** Gold-standard evaluation where every detail matters. Understands nuance, factual correctness, and qualitative differences that embeddings alone can't capture.

### Automatic Fallback

The default scorer is `auto` — it tries semantic first, and if that fails (e.g., model not installed), falls back to lexical. You configure this via the `FM_DIVERGENCE_SCORER` environment variable.

### Additional Comparison Features

- **Inline Diffs** — Word-level diff highlighting (like GitHub PRs) showing exactly what changed between responses. Cached in Redis for 24 hours.
- **Divergence Summary** — A one-sentence human-readable description of the key differences.

---

## Part 6 — The Evaluator System (Advanced)

Beyond divergence scoring (how different are two responses?), Forkmark also provides **evaluators** (how *good* is a response?). These are pluggable, registrable functions that score outputs.

### Built-in Evaluators

#### Deterministic Evaluators (instant, no AI needed)

| Evaluator | What it checks | Example use |
|---|---|---|
| `json_schema` | Is the output valid JSON? Does it match a schema? | API response generation |
| `regex_match` | Does the output match a regex pattern? (ReDoS-protected) | Format validation |
| `exact_match` | Is the output exactly equal to an expected string? | Classification tasks |
| `contains` | Does the output contain a specific substring? | Keyword presence |
| `max_length` | Is the output under N characters? | Tweet generation |
| `latency_check` | Did the response arrive within N milliseconds? | SLA enforcement |

#### LLM-Based Evaluators (use a judge model)

| Evaluator | What it checks | Example use |
|---|---|---|
| `faithfulness` | Is the output grounded in provided context? (no hallucination) | RAG pipelines |
| `relevance` | Does the output actually answer the question asked? | Q&A systems |
| `toxicity` | Is the content safe and appropriate? | Customer-facing chatbots |

#### Pairwise Evaluators (compare two responses head-to-head)

| Evaluator | What it checks | Example use |
|---|---|---|
| `pairwise_preference` | Which response is better overall? (with position debiasing) | General quality |
| `pairwise_conciseness` | Which is more concise? | Summarization |
| `pairwise_expected_match` | Which is closer to a known-good answer? | Regression testing |

### Position Debiasing

The `pairwise_preference` evaluator uses a technique from the MT-Bench paper: it runs the judge **twice** with the responses in swapped order. If the judge picks the same winner both times, the result is high-confidence. If it flips, the result is flagged as uncertain. This eliminates the bias LLMs have toward the first option presented.

### Custom Evaluators

You can register your own evaluators at runtime:

```python
from core.evaluators import register_evaluator

@register_evaluator("brand_voice")
def check_brand_voice(output: str, **kwargs) -> dict:
    """Check if the output matches our brand's tone."""
    brand_words = ["innovative", "seamless", "empower"]
    score = sum(1 for w in brand_words if w in output.lower()) / len(brand_words)
    return {
        "score": score,
        "passed": score > 0.5,
        "detail": f"Found {int(score * len(brand_words))}/{len(brand_words)} brand keywords"
    }
```

---

## Part 7 — The Python SDK (Advanced)

The [SDK](file:///Users/ambarmore/forkmark/v0.1.2/sdk/) (`pip install forkmark`) is the primary way to integrate Forkmark into your workflows programmatically.

### Installation

```bash
pip install forkmark                    # Core SDK
pip install forkmark[openai]            # + OpenAI wrapper
pip install forkmark[anthropic]         # + Anthropic wrapper
pip install forkmark[langchain]         # + LangChain callback handler
pip install forkmark[all]               # Everything
```

### Quick Start: Single A/B Comparison

```python
import forkmark
from openai import OpenAI

forkmark.init(api_key="fm_your_key", base_url="http://localhost:7700")
openai = OpenAI()

prompt = "Explain what a database index is to a junior developer."

with forkmark.run(workflow="db-explainer-test") as wf:
    # Branch A — GPT-4o with basic prompt
    resp_a = openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    wf.step(input=prompt, output=resp_a.choices[0].message.content)

    # Branch B — GPT-4o-mini with detailed system prompt
    resp_b = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Use analogies. Keep it under 100 words."},
            {"role": "user", "content": prompt}
        ]
    )
    wf.branch_step(input=prompt, output=resp_b.choices[0].message.content)

# Forkmark automatically creates the comparison and begins scoring
```

### Batch Evaluation with Eval Runs

```python
import forkmark

forkmark.init(api_key="fm_your_key")

test_cases = [
    "What is a foreign key?",
    "Explain CAP theorem",
    "When should I use NoSQL?",
    # ... 97 more
]

with forkmark.eval_run(name="SQL Expert v2 vs v1", test_set_id="ts_abc") as er:
    # Sequential execution
    for case in er:
        resp_a = call_model_a(case.input)
        resp_b = call_model_b(case.input)
        case.step(input=case.input, output=resp_a)
        case.branch_step(input=case.input, output=resp_b)

    # Or parallel execution (4-10x faster):
    # er.run(my_comparison_fn, max_workers=8)
```

### Drop-In Provider Wrappers

The SDK provides wrappers that automatically log steps to Forkmark:

```python
from forkmark.integrations import ForkmarkOpenAI

# Drop-in replacement for OpenAI client
client = ForkmarkOpenAI()

# Every call is automatically logged as a step
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
# Supports sync, async, and streaming
```

### Agent Comparison (v0.1.2)

```python
import forkmark

with forkmark.agent_run(workflow="research-agent-test") as ar:
    # Branch A: Agent with ReAct prompting
    with ar.branch_a() as recorder_a:
        with recorder_a.nested("reasoning"):
            recorder_a.event("reasoning", detail="Planning search strategy...")
        with recorder_a.nested("tool_call"):
            recorder_a.event("tool_call", name="google_search", input="latest AI news")
            recorder_a.event("tool_result", output="Found 5 articles...")
        recorder_a.event("decision", detail="Synthesizing findings...")

    # Branch B: Agent with chain-of-thought prompting
    with ar.branch_b() as recorder_b:
        recorder_b.event("reasoning", detail="Breaking down the question...")
        recorder_b.event("tool_call", name="web_browse", input="arxiv.org/AI")
        recorder_b.event("tool_result", output="Found 3 papers...")
        recorder_b.event("reasoning", detail="Cross-referencing sources...")

# Forkmark compares trajectories: tool sequence alignment,
# outcome equivalence, and efficiency ratio
```

---

## Part 8 — REST API Reference (Advanced)

The backend exposes a REST API with 62 endpoints across 16 route modules. Full OpenAPI docs are available at `http://localhost:7700/docs`.

### Key Endpoint Groups

#### SDK Endpoints (authenticated via `X-API-Key`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sdk/eval-runs` | Create an eval run |
| `POST` | `/api/sdk/runs` | Create a workflow run |
| `POST` | `/api/sdk/branches` | Create a branch |
| `POST` | `/api/sdk/steps` | Log a single step output |
| `POST` | `/api/sdk/steps/batch` | Log multiple step outputs at once |
| `POST` | `/api/sdk/comparisons` | Create a comparison between branches |

#### Comparison & Decision

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/comparisons` | List comparisons with inline diffs |
| `GET` | `/api/comparisons/<id>` | Get comparison detail with scoring status |
| `POST` | `/api/comparisons/<id>/decision` | Record a human decision |
| `PUT` | `/api/comparisons/<id>/decision` | Update a decision |

#### Export

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/decisions/export?format=dpo` | Export as DPO training data |
| `GET` | `/api/decisions/export?format=openai_ft` | Export in OpenAI fine-tuning format |
| `GET` | `/api/decisions/export?format=jsonl` | Export as JSONL |
| `GET` | `/api/decisions/export?format=csv` | Export as CSV |
| `GET` | `/api/exports/preference-corpus` | Rich export with reviewer metadata and provenance |

#### No-Code Runner & Playground

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/runner` | Run a multi-step workflow with 2 branches (no code required) |
| `POST` | `/api/playground` | Quick single-prompt A/B comparison |

#### Agent Comparison (v0.1.2)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/agent/trace-events/batch` | Submit agent trace events |
| `POST` | `/api/agent/trajectory-score` | Score a trajectory comparison |
| `GET` | `/api/agent/trajectory-outcomes/<id>` | Get trajectory scoring results |

#### Health & Operations

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness probe (Kubernetes) |
| `GET` | `/readyz` | Readiness probe (checks DB + Redis + PgBouncer) |
| `GET` | `/api/stats` | Dashboard statistics (cached 15s) |
| `GET` | `/api/stats/charts` | Chart data (divergence histogram, cost over time) |
| `POST` | `/api/admin/prune` | Delete step outputs older than N days |

### Authentication

Three authentication mechanisms, used in different contexts:

| Mechanism | Header | Use Case |
|---|---|---|
| **API Key** | `X-API-Key: fm_...` | SDK integration, CI/CD pipelines |
| **JWT (Device Flow)** | `Authorization: Bearer <token>` | Desktop apps, CLI tools (RFC 8628) |
| **CI Token** | `X-CI-Token: <hmac>` | Automated test suites in CI |

API keys are hashed with **Argon2id** and verified against an LRU cache (2048 entries, 60s TTL) for performance.

---

## Part 9 — Frontend UI (Intermediate)

The frontend is a React Single-Page Application with 16 views, all lazy-loaded for performance.

### Key Views

#### Dashboard
Your home base. Shows:
- Stat cards (total eval runs, comparisons, decisions, average divergence)
- **Divergence histogram** (Recharts bar chart showing distribution of scores)
- **Cost over time** (Recharts line chart tracking LLM spend)
- Tables of recent eval runs, workflows, and pending reviews

#### Workflow Builder
The most powerful view — two modes:

- **No-Code Mode** — A form where you configure two branches (model, temperature, max tokens, system prompt), add test cases, and click "Run." No coding required.
- **Developer Mode** — Generates a ready-to-use Python SDK snippet based on your configuration. Copy-paste and run.

#### Playground
The quickest way to compare: type a single prompt, pick two models, hit Run, and see responses + divergence score side by side. Great for ad-hoc exploration.

#### Branch Compare (Core Review UI)
Where the human review happens:
- Side-by-side response display with **inline diffs** (word-level, like GitHub)
- Divergence score badge (color-coded: green/orange/red)
- **Sticky decision panel** — pick A/B/tie/skip, set confidence, write rationale, add tags
- **Keyboard shortcuts** for fast reviewing: `A/1` = Branch A, `B/2` = Branch B, `N/3` = Neither, `H/M/L` = confidence
- Threaded comments for collaboration
- Cost estimation per response

#### Agent Trajectory Compare (v0.1.2)
Side-by-side timeline of agent trace events, color-coded by type:
- 🟣 Reasoning
- 🟢 Tool call
- 🔵 Tool result
- 🩷 Sub-agent
- 🔴 Error

Shows trajectory scores (tool sequence alignment, outcome equivalence, efficiency) and clickable event detail panel.

#### Decision History
Browse and filter all decisions by workflow, choice, confidence, and divergence range. Export buttons for DPO, OpenAI fine-tuning, JSONL, and CSV.

#### Demo Gallery
9 pre-built industry demo scenarios (healthcare, legal, finance, retail, HR, sales, engineering, plus 3 agent demos). One-click seeding to explore the platform with realistic data.

### Design System

- **Dark theme** by default with CSS custom properties (`--bg`, `--surface`, `--accent`, `--green`, `--red`)
- **Inter font** for modern typography
- **Responsive breakpoints** at 1100px, 900px, 600px
- **Accessibility**: Skip-nav link, `aria-*` attributes, keyboard shortcuts, `focus-visible` outlines (WCAG 2.1 AA)
- **Collapsible sidebar** with tooltips in collapsed mode
- **Error boundaries** around every view with toast notifications

---

## Part 10 — Agent Trajectory Comparison In-Depth (v0.1.2 Feature)

### The Problem

Traditional LLM evaluation compares single prompt→response pairs. But modern AI agents perform multi-step workflows: they *reason*, *decide which tools to call*, *interpret results*, and *iterate*. Comparing just the final output misses the journey.

### The Solution

Forkmark v0.1.2 introduces **trajectory comparison** — evaluating the entire sequence of an agent's decisions.

### Data Model

Each agent action is a `TraceEvent`:

```python
TraceEvent(
    event_type="tool_call",       # reasoning | tool_call | tool_result |
                                  # sub_agent | observation | decision | error
    name="google_search",         # tool name or label
    input="latest AI papers",     # what was sent
    output="Found 5 results...",  # what came back
    parent_event_id="evt_001",    # for nested events (tree structure)
    latency_ms=1200,
    token_count=450,
    cost_usd=0.0023
)
```

Events form a **tree** (via `parent_event_id`), not just a flat list — capturing nested tool calls and sub-agent invocations.

### Scoring Dimensions

| Dimension | Weight | How It Works |
|---|---|---|
| **Tool Sequence Alignment** | 35% | Normalized Levenshtein distance on the ordered list of tool/event names. Measures: "Did both agents use similar tools in similar order?" |
| **Outcome Equivalence** | 45% | Applies the divergence scorer (semantic, lexical, etc.) to the final outputs. Measures: "Did they arrive at the same answer?" |
| **Efficiency Ratio** | 20% | Weighted comparison of cost (35%), latency (25%), tokens (25%), and tool count (15%). Measures: "Which was faster/cheaper?" |

**Overall trajectory score** = weighted mean of all three dimensions. The tree is walked depth-first to extract tool sequences.

---

## Part 11 — Enterprise & Multi-Tenancy (Expert)

When `FM_ENTERPRISE_MODE=true`, Forkmark unlocks additional capabilities for organizations:

### Multi-Tenant Workspace Isolation

Each workspace gets its own **PostgreSQL schema** (`search_path`). Cross-workspace data access is impossible at the database level. SQLite falls back to single-tenant mode.

### RBAC (Role-Based Access Control)

| Role | Permissions |
|---|---|
| `org_admin` | Full access across all workspaces |
| `ws_admin` | Full access within one workspace |
| `evaluator` | Review comparisons, record decisions, export data |
| `viewer` | Read-only access |
| `sdk_only` | API access only (no UI) |

**Sandbox workspaces** can be created where DPO export, decision recording, and deletion are all blocked — useful for demos or restricted environments.

### Data Consent & Privacy (GDPR)

- Reviewers explicitly opt in/out per workflow for: training data, anonymized export, aggregated stats
- Consent is revocable at any time
- Export endpoints filter by consent status
- Preference corpus export supports anonymization

### Audit Logging

23 action types logged immutably: authentication, workspace CRUD, data operations, settings changes, SCIM provisioning events. Queryable with wildcard filters, CSV exportable, with configurable retention purge.

### SCIM 2.0 Provisioning

Integration with WorkOS for automated user provisioning via SCIM webhooks — onboard/offboard users from your identity provider (Okta, Azure AD, etc.).

### Data Residency

Region-aware database and Redis routing (US, EU, APAC) via `FM_REGION` and per-region connection strings.

### Observability Stack

Three pillars:
1. **Structured logging** — JSON format with correlation IDs
2. **Prometheus metrics** — Counters and histograms with p50/p95/p99 percentiles, scrapeable at `/metrics`
3. **OpenTelemetry tracing** — GenAI semantic conventions (`gen_ai.*` attributes), integrates with LangChain/LlamaIndex distributed traces

---

## Part 12 — Configuration & Deployment (Expert)

### Configuration Reference

All configuration is via environment variables (or `~/.forkmark/.env`):

| Category | Variable | Default | Description |
|---|---|---|---|
| **Server** | `FM_HOST` | `127.0.0.1` | Bind address |
| | `FM_PORT` | `7700` | Port |
| **Database** | `FM_DB_PATH` | `~/.forkmark/forkmark.db` | SQLite path |
| | `FM_DATABASE_URL` | — | PostgreSQL connection string (enables Postgres) |
| **Scoring** | `FM_DIVERGENCE_SCORER` | `auto` | `auto`, `lexical`, `semantic`, `openai`, `llm_judge` |
| | `FM_ST_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| | `FM_JUDGE_MODEL` | `gpt-4o-mini` | LLM judge model |
| **Background** | `FM_BACKGROUND_WORKERS` | `4` | Scoring worker count (1–16) |
| | `FM_CELERY_BROKER_URL` | — | Redis URL for Celery |
| **Auth** | `FM_SECRET_KEY` | — | Fernet key for encrypting provider credentials |
| | `FM_REQUIRE_UI_AUTH` | `false` | Require API key for UI access |
| | `FM_BOOTSTRAP_TOKEN` | — | Token for creating first API key |
| **Rate Limiting** | `FM_RATE_LIMIT` | `1000` | Requests per minute per API key |
| **Redis** | `FM_REDIS_URL` | — | Redis connection (caching, rate limiting, message bus) |
| **Enterprise** | `FM_ENTERPRISE_MODE` | `false` | Enable multi-tenancy, SCIM, device flow, data residency, OTel |
| | `FM_MULTI_TENANT` | `false` | PostgreSQL schema-level isolation |
| | `FM_ENABLE_OTEL` | `false` | OpenTelemetry tracing |
| **Agent** | `FM_ENABLE_AGENT_COMPARISON` | `true` | Enable v0.1.2 agent trajectory features |

### Deployment Options

#### 1. Local Development (Zero Config)

```bash
cd forkmark/v0.1.2
python start.py
# → Starts on http://localhost:7700
# → SQLite database at ~/.forkmark/forkmark.db
```

Single Python process serves both the API and the React SPA. No Redis, no external database.

#### 2. Docker Compose (Recommended for Teams)

```yaml
# docker-compose.simple.yml
services:
  forkmark:
    build: .
    ports:
      - "7700:7700"
    volumes:
      - forkmark_data:/root/.forkmark
    environment:
      - FM_DIVERGENCE_SCORER=semantic
```

#### 3. Production (Nginx + PostgreSQL + Redis + Celery)

```
                   ┌──────────┐
  Internet ───────▶│  Nginx   │──── TLS termination
                   └────┬─────┘
                        │
              ┌─────────▼──────────┐
              │  Forkmark (uvicorn)│  ← horizontally scalable
              │  FastAPI backend    │
              └──┬──────────┬──────┘
                 │          │
      ┌──────────▼──┐  ┌───▼───────────┐
      │ PostgreSQL  │  │     Redis      │
      │ (PgBouncer) │  │  Cache + Celery│
      └─────────────┘  └───┬───────────┘
                            │
                    ┌───────▼────────┐
                    │ Celery Workers  │  ← scalable scoring workers
                    └────────────────┘
```

#### 4. Kubernetes

Health endpoints for orchestration:
- `/healthz` — liveness probe (always 200)
- `/readyz` — readiness probe (checks DB, Redis, PgBouncer connectivity)
- `/api/health` — detailed health with pool stats

---

## Part 13 — What's New in v0.1.2

Based on the [CHANGELOG](file:///Users/ambarmore/forkmark/v0.1.2/CHANGELOG.md):

### Major Additions
- **Agent Trajectory Comparison** — Compare multi-step agent workflows across three scoring dimensions (tool sequence, outcome, efficiency)
- **Trace Event Model** — Tree-structured trace events with 7 event types
- **`TrajectoryRecorder` SDK** — Context managers for recording agent traces with nested event support
- **Agent Demo Scenarios** — Three pre-built agent comparison demos (code review, research, support)

### Infrastructure
- **Feature Flags** — Three-level gating: env var → org plan tier → workspace override
- **Enhanced Observability** — GenAI semantic conventions for OpenTelemetry spans

---

## Glossary

| Term | Definition |
|---|---|
| **Branch** | One configuration variant in a comparison (always exactly two: A=baseline, B=challenger) |
| **Comparison** | A side-by-side pairing of Branch A and Branch B outputs for the same input |
| **Decision** | A human reviewer's verdict on a comparison (A/B/tie/skip with confidence and rationale) |
| **Divergence Score** | A 0–1 measure of how different two responses are (0=identical, 1=completely different) |
| **DPO** | Direct Preference Optimization — a technique for fine-tuning AI models using human preference data |
| **Eval Run** | A batch evaluation: N test cases × 2 branch configurations, producing N comparisons |
| **Evaluator** | A pluggable function that scores an AI output (e.g., json_schema, faithfulness, toxicity) |
| **Fork** | The act of splitting a workflow into two branches for comparison |
| **Inline Diff** | Word-level highlighting showing exactly what changed between two responses |
| **Persona** | A pre-configured system prompt template (not a core feature in v0.1.2) |
| **Provider** | An AI service (OpenAI, Anthropic, etc.) configured in Forkmark's provider registry |
| **RLHF** | Reinforcement Learning from Human Feedback — using human preferences to train AI models |
| **Step Output** | The result of one LLM call within a branch (text, tokens used, latency, cost) |
| **Test Case** | A single input prompt used in an evaluation |
| **Test Set** | A named, versioned, and freezable collection of test cases |
| **Token** | The smallest unit of text an AI model processes (~¾ of a word); used for pricing |
| **Trace Event** | One step in an agent's trajectory (reasoning, tool_call, tool_result, sub_agent, etc.) |
| **Trajectory** | The complete sequence of trace events an agent produces while solving a task |
| **Workflow** | A named grouping of related runs (e.g., "customer-support-v3-evaluation") |
| **Workspace** | A tenant-isolated environment in enterprise mode (maps to a PostgreSQL schema) |

---

## Summary

**Forkmark is a self-hosted A/B testing platform for AI.** It structures the messy process of evaluating AI outputs into a repeatable, evidence-based workflow:

```
  Define Test Cases  ──▶  Run Through 2 Branches  ──▶  Score Divergence
         │                                                      │
         │                                                      ▼
         │                                              Review Side-by-Side
         │                                                      │
         │                                                      ▼
         │                                              Record Decisions
         │                                                      │
         ▼                                                      ▼
  Export Training Data  ◀──────────────────────────  Analyze Results
         │
         ▼
  Fine-Tune Model  ──▶  New Baseline  ──▶  (repeat)
```

Whether you're choosing between AI providers, testing prompt changes, evaluating RAG pipelines, comparing autonomous agents, or building training datasets for fine-tuning — Forkmark gives you the infrastructure to make these decisions with data, not vibes.
