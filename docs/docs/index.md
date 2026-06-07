# Forkmark

**The eval-first A/B comparison platform for LLM workflows.**

Forkmark makes structured human evaluation the core primitive of your AI quality process. Instead of bolting evaluation onto logging, Forkmark builds the comparison-decision loop into every workflow: run two model configurations side-by-side, score divergence automatically, and collect structured human verdicts with confidence and rationale.

## Why Forkmark?

- **Pairwise A/B evaluation** with position debiasing (dual-run swap, MT-Bench technique)
- **Four-tier divergence scoring** — lexical, semantic, OpenAI embeddings, LLM-as-judge
- **Structured decisions** — choice, confidence level, rationale for and against
- **Preference data flywheel** — consent-gated DPO/RLHF exports as a byproduct of quality review
- **Enterprise-ready** — multi-tenant PostgreSQL isolation, SCIM 2.0 provisioning, RBAC, data residency, audit logging

## Quick start

```bash
# Clone and start
git clone https://github.com/forkmark/forkmark.git
cd forkmark
python start.py
```

Then instrument your first workflow:

```python
import forkmark

forkmark.init(api_key="fm_...", workflow="my-workflow")

with forkmark.run("my-workflow", input_data={"question": "What is ML?"}) as wf:
    out_a = wf.step("answer", model="gpt-4o-mini", messages=[...], call_fn=my_llm_fn)
    out_b = wf.branch_step("answer", model="gpt-4o", messages=[...], call_fn=my_llm_fn)

# Open http://localhost:7700 to compare outputs and record your verdict.
```

## Architecture overview

```
TestSet → TestCase → EvalRun → WorkflowRun → Branch (A/B)
    → StepOutput → Comparison → Decision
```

Every entity is richly typed with metadata. Comparisons get automatic divergence scores. Decisions capture structured human preference with confidence and rationale — the building blocks of DPO training data.

## Next steps

- [Quickstart guide](getting-started/quickstart.md) — up and running in 5 minutes
- [SDK overview](sdk/overview.md) — instrument your workflows
- [API reference](api/endpoints.md) — full endpoint documentation
- [Deployment guide](deployment/self-hosted.md) — production setup
