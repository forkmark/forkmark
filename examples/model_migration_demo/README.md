# Model Migration Demo — StyleForge Commerce

This demo shows how a real company integrates Forkmark into an existing AI workflow
to de-risk a model upgrade — without changing the production code until they're confident.

---

## The Scenario

**StyleForge Commerce** runs an AI-powered product content pipeline that processes raw
supplier data (SKUs, specs, supplier titles) and generates customer-facing copy:
category classification, SEO titles, product descriptions, and meta tags.

The pipeline currently runs on **`gpt-3.5-turbo`**. The engineering team wants to
evaluate **`gpt-4o-mini`** — cheaper per token, reportedly better at structured JSON —
but they need evidence before touching production.

**The question Forkmark answers:**
> "Does gpt-4o-mini produce materially better product content, or is it just different?"

---

## Files in This Demo

```
model_migration_demo/
├── workflow_original.py          # The production pipeline — no Forkmark
├── workflow_with_forkmark.py    # The same pipeline + Forkmark integration (~50 new lines)
├── seed_demo.py                  # Pre-baked comparison data — no API key needed
├── run_live_comparison.py        # Runs both models live — needs OPENAI_API_KEY
└── README.md                     # This file
```

---

## The Production Pipeline (`workflow_original.py`)

This is the pipeline StyleForge runs today. It's production-grade Python:

- `PipelineConfig` dataclass — all settings in one place
- `OpenAIClient` — httpx + tenacity retry (3 attempts, exponential backoff)
- `ProductContentPipeline` — four sequential steps per product:

| Step | What it does |
|------|-------------|
| `classify_product` | Extracts canonical category, product type, key features, USP |
| `generate_title` | Writes SEO-optimised title + 2 alternatives |
| `generate_description` | Writes headline, body paragraphs, 5 benefit bullets |
| `generate_seo_meta` | Writes meta title, meta description, 10 keywords |

Each step's output feeds the next (classification informs the title, title informs description, etc.).

Run it standalone:

```bash
export OPENAI_API_KEY=sk-...
python workflow_original.py               # all 10 sample products
python workflow_original.py --sku SUP-0042
python workflow_original.py --model gpt-4o-mini --dry-run
```

---

## Adding Forkmark (`workflow_with_forkmark.py`)

The Forkmark-enabled version makes **4 additions** to the original file.
The core pipeline logic — every prompt, every step, every data model — is untouched.

### What changed

**1. Import the Forkmark SDK** (+2 lines)
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
from forkmark.client import ForkmarkClient
```

**2. Two new config fields** (+3 lines)
```python
forkmark_api_key: str = field(default_factory=lambda: os.environ.get("FORKMARK_API_KEY", ""))
forkmark_url:     str = "http://127.0.0.1:7700"
```

**3. Initialise Forkmark on startup** (+3 lines in `__init__`)
```python
self.fp = ForkmarkClient(api_key=config.forkmark_api_key, base_url=config.forkmark_url, ...)
self._eval_run_id = self._init_eval_run()
```

**4. New method: `process_with_comparison()`** (~40 lines)

Instead of running the pipeline once, it:
1. Creates a Forkmark run for this product
2. Creates **Branch A** (baseline: `gpt-3.5-turbo`) and **Branch B** (challenger: `gpt-4o-mini`)
3. Runs `_run_model()` for both models in sequence
4. Logs all four steps to Forkmark for both branches
5. Calls `create_comparison()` — Forkmark computes divergence scores
6. Returns the baseline model's output (production is unaffected)

The original `process()` method still exists and still works. The new method is additive.

### Visual diff

```
workflow_original.py              workflow_with_forkmark.py
─────────────────────────────────────────────────────────────
class ProductContentPipeline:     class ProductContentPipelineWithForkmark:

  def __init__(self, config):       def __init__(self, config):
    self.llm = OpenAIClient(...)      self.llm = OpenAIClient(...)
                                 +    self.fp  = ForkmarkClient(...)        ← NEW
                                 +    self._eval_run_id = self._init_eval_run()  ← NEW

  def process(self, product):       def process_with_comparison(self, product):
    result = self._run_model(p)  -    result = self._run_model(p)
                                 +    run = self.fp.start_run(...)            ← NEW
                                 +    branch_a = self.fp.create_branch(...)   ← NEW
                                 +    branch_b = self.fp.create_branch(...)   ← NEW
                                 +    outputs_a = self._run_model(p, baseline)
                                 +    outputs_b = self._run_model(p, challenger)
                                 +    for step in steps:
                                 +        self.fp.log_step(branch_a, ...)     ← NEW
                                 +        self.fp.log_step(branch_b, ...)     ← NEW
                                 +    self.fp.create_comparison(...)          ← NEW
    return result                     return result  # baseline output only
```

Production still runs on the baseline model. Forkmark is purely observational.

---

## Running the Demo

### Option A — No API key needed (recommended for first look)

```bash
cd forkmark
uvicorn backend.main:app --reload --port 7700   # terminal 1
cd frontend && npm run dev                       # terminal 2

cd examples/model_migration_demo
python seed_demo.py
```

This seeds 10 pre-baked product comparisons (gpt-3.5-turbo vs gpt-4o-mini outputs
written by hand to show the kind of divergence you'd see in practice). No API calls made.

Open `http://localhost:5173` → Eval Runs → "gpt-3.5-turbo vs gpt-4o-mini — Product Content Migration"

### Option B — Live comparison (needs OPENAI_API_KEY)

```bash
export OPENAI_API_KEY=sk-...
export FORKMARK_API_KEY=fm_...       # bootstrap from Forkmark UI or API

cd examples/model_migration_demo
python run_live_comparison.py --sku SUP-0042    # smoke test one product first
python run_live_comparison.py                   # all 10 products
```

The script runs pre-flight checks, shows estimated API cost, asks for confirmation
before processing all products, then streams live results to Forkmark.

### Option C — Integrate into your own workflow

Copy `workflow_with_forkmark.py` as a reference. The integration pattern is:

```python
# Startup
pipeline = ProductContentPipelineWithForkmark(config)

# Per item (replaces your existing process() call)
result = pipeline.process_with_comparison(product)

# After all items
pipeline.finish_eval_run(total_cases=n)
```

---

## What You See in Forkmark

After seeding (Option A) or running live (Option B):

**Eval Run overview**
- 10 products compared
- Divergence histogram across all cases — which products changed most?
- Step-level breakdown — which pipeline step diverges most?

**Per-product review**

For each product you'll see Branch A and Branch B outputs side-by-side:

| Step | Branch A (gpt-3.5-turbo) | Branch B (gpt-4o-mini) |
|------|--------------------------|------------------------|
| classify_product | Generic categorisation | Richer feature extraction |
| generate_title | Adequate, keyword-stuffed | Specific, benefit-led |
| generate_description | Bullet-list boilerplate | Conversational, spec-accurate |
| generate_seo_meta | Generic keywords | Long-tail, intent-matched |

**Human review queue**
- Sorted by divergence score — highest-divergence cases first
- For each case: record `A wins`, `B wins`, `tie`, or `skip`
- Win rate tracked in real time

---

## Making the Migration Decision

After reviewing ≥60% of cases, check the win rate in Forkmark.

```
If gpt-4o-mini (Branch B) wins on >60% of human reviews:
  → Open workflow_original.py
  → Change line 19:  model: str = "gpt-3.5-turbo"
  → To:              model: str = "gpt-4o-mini"
  → Deploy. One-line change, de-risked by this eval.

If gpt-3.5-turbo (Branch A) wins, or results are mixed:
  → Keep the current model
  → The eval data is saved — revisit when gpt-4o-mini improves
  → Or test a different prompt rather than a different model

If divergence is low across all steps:
  → The models are producing similar outputs
  → Switch is low-risk either way — cost/latency may be the deciding factor
```

The Forkmark eval run persists. You can return to it weeks later, add more reviewers,
or re-run it with updated prompts.

---

## Products in the Demo

| SKU | Product | Key divergence |
|-----|---------|---------------|
| SUP-0042 | Wireless Bluetooth Headphones | Commuter vs "wireless headphones" framing |
| SUP-1183 | Wireless Charging Pad | MFi certification detail, charging speed specificity |
| SUP-2291 | Trail Running Shoes | Pronation/stability detail, terrain specificity |
| SUP-3047 | GPS Smartwatch | Health metric accuracy, GPS chip naming |
| SUP-4102 | Drip Coffee Maker | Bloom time, extraction curve language |
| SUP-5234 | Merino Wool Jumper | 18.5-micron fibre detail vs "soft wool" |
| SUP-6817 | Yoga Mat | Alignment line utility, grip compound naming |
| SUP-7390 | Hyaluronic Acid Serum | Molecular weight science, HA mechanism |
| SUP-8044 | LED Desk Lamp | Colour rendering index, Kelvin range |
| SUP-9156 | Resistance Band Set | Load range specificity, progressive overload framing |

---

## Key Takeaway

The integration surface is small — ~50 lines added to a 350-line production script.
The pipeline continues running normally; Forkmark captures both outputs in the background.
The team gets structured, human-reviewed evidence before touching a single line of production config.

This is the Forkmark pattern: **run both, review the diff, decide with data.**
