# Export Formats

Forkmark exports preference data in multiple formats for model training, analysis, and compliance.

## DPO format

Direct Preference Optimization training data. Each line contains a prompt, the chosen (winning) output, and the rejected (losing) output.

```bash
curl "http://localhost:7700/api/decisions/export/dpo?workflow_id=WF_ID&min_confidence=high" \
  -H "X-API-Key: fm_..."
```

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `workflow_id` | string | Filter by workflow |
| `eval_run_id` | string | Filter by eval run |
| `min_confidence` | string | Minimum confidence: `low`, `medium`, `high`, `definitive` |
| `min_divergence` | float | Minimum divergence score (0.0–1.0) |
| `require_consent` | bool | Only export workflows with active `training_data` consent |

**Output (JSONL):**

```json
{"prompt": "{\"question\": \"What is ML?\"}", "chosen": "Machine learning is...", "rejected": "ML stands for...", "metadata": {"comparison_id": "...", "confidence": "high", "divergence_score": 0.73}}
```

## OpenAI fine-tuning format

Chat completion format compatible with OpenAI's fine-tuning API:

```bash
curl "http://localhost:7700/api/decisions/export/openai-ft?eval_run_id=ER_ID" \
  -H "X-API-Key: fm_..."
```

**Output (JSONL):**

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

## Preference corpus

The richest export format, designed for B2B data licensing. Includes reviewer metadata, confidence, structured rationale, divergence score, and data category.

```bash
curl "http://localhost:7700/api/preference-corpus?anonymize=true&require_consent=true" \
  -H "X-API-Key: fm_..."
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow_id` | string | — | Filter by workflow |
| `anonymize` | bool | `true` | Replace raw prompts with provenance hashes |
| `require_consent` | bool | `false` | Skip workflows without active `training_data` consent |

**Output (JSONL):**

```json
{
  "provenance_hash": "a1b2c3...",
  "prompt": "a1b2c3...",
  "chosen": "...",
  "rejected": "...",
  "rationale_for_choice": "Output A was more concise and accurate",
  "rationale_for_rejection": "Output B hallucinated a statistic",
  "confidence": "high",
  "tags": ["support", "classification"],
  "data_category": "customer-support",
  "divergence_score": 0.73,
  "reviewer": {
    "role": "domain_expert",
    "expertise_level": "senior",
    "domain_expertise": ["nlp", "support"]
  }
}
```

## Raw decisions

All decision fields without training-data formatting:

```bash
curl "http://localhost:7700/api/decisions/export?workflow_id=WF_ID" \
  -H "X-API-Key: fm_..."
```

## Data consent

Exports that touch preference data can be gated by consent records. Create consent before exporting:

```bash
curl -X POST http://localhost:7700/api/consent \
  -H "X-API-Key: fm_..." \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "workflow_id": "WF_ID",
    "consent_type": "training_data",
    "granted_by": "legal@company.com",
    "notes": "Approved for internal model training"
  }'
```

Consent types: `training_data`, `anonymized_export`, `aggregated_stats`.
