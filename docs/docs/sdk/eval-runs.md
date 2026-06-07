# Eval Runs

Eval runs execute batch evaluations over a list of test inputs. Each input runs through both branch configurations, producing comparisons for systematic human review.

## Basic usage

```python
import forkmark

forkmark.init(api_key="fm_...", workflow="support-triage")

test_cases = [
    {"input": {"ticket": "Order never arrived"}, "label": "shipping-delay"},
    {"input": {"ticket": "Wrong item received"}, "label": "wrong-item"},
    {"input": {"ticket": "Refund not processed"}, "label": "refund-issue"},
]

with forkmark.eval_run(
    name="GPT-4o-mini vs GPT-4o — Q3 support tickets",
    workflow="support-triage",
    branch_a={"label": "GPT-4o-mini", "model_id": "gpt-4o-mini", "temperature": 0.3},
    branch_b={"label": "GPT-4o", "model_id": "gpt-4o", "temperature": 0.3},
    inputs=test_cases,
    description="Comparing model quality on Q3 support ticket classification",
) as er:
    for case in er:
        out_a = case.step(
            "classify",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Classify: {case.input['ticket']}"}],
            call_fn=my_llm_call,
        )
        out_b = case.branch_step(
            "classify",
            model="gpt-4o",
            messages=[{"role": "user", "content": f"Classify: {case.input['ticket']}"}],
            call_fn=my_llm_call,
        )

print(f"Done — {er.stats['completed']} cases. Open Forkmark UI to review.")
```

## Test sets

Test sets are versioned collections of test inputs. Create them via the API or UI, then reference them in eval runs:

```python
# Create a test set via the API
import httpx

client = httpx.Client(base_url="http://localhost:7700", headers={"X-API-Key": "fm_..."})

# Create the test set
ts = client.post("/api/test-sets", json={"name": "Q3 Support Tickets", "workflow_id": "support-triage"}).json()

# Add cases
client.post(f"/api/test-sets/{ts['id']}/cases/bulk", json={
    "cases": [
        {"input_data": {"ticket": "Order delayed"}, "label": "shipping", "domain": "logistics"},
        {"input_data": {"ticket": "Wrong item"}, "label": "fulfillment", "domain": "logistics"},
    ]
})
```

### Freezing test sets

When you start an eval run, Forkmark auto-freezes the test set to prevent modifications that would invalidate results. Creating a new version from a frozen set copies all cases:

```bash
# Version a frozen test set
curl -X POST http://localhost:7700/api/test-sets/{ts_id}/version \
  -H "X-API-Key: fm_..." \
  -H "Content-Type: application/json"
```

## Viewing results

After an eval run completes:

1. Open the Forkmark UI at `http://localhost:7700`
2. Navigate to **Eval Runs**
3. Click your eval run to see all comparisons sorted by divergence score
4. Review comparisons from highest divergence (most interesting) to lowest
5. Record decisions with choice, confidence, and rationale

## Exporting results

```bash
# Raw decisions
curl http://localhost:7700/api/eval-runs/{er_id}/export \
  -H "X-API-Key: fm_..."

# DPO training data (prompt/chosen/rejected)
curl "http://localhost:7700/api/decisions/export/dpo?eval_run_id={er_id}&min_confidence=high" \
  -H "X-API-Key: fm_..."

# OpenAI fine-tuning format
curl "http://localhost:7700/api/decisions/export/openai-ft?eval_run_id={er_id}" \
  -H "X-API-Key: fm_..."
```

See [Export formats](../api/exports.md) for details.
