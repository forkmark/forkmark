# Pairwise Evaluation

Pairwise evaluation is Forkmark's core differentiator. Instead of scoring outputs individually, it compares two outputs head-to-head — the same technique validated by the MT-Bench paper (Zheng et al., 2023).

## Position debiasing

LLMs exhibit position bias when asked to compare two texts: they tend to prefer whichever is presented first. Forkmark eliminates this with dual-run swap:

1. **Run 1**: Present Output A first, Output B second. Record the verdict.
2. **Run 2**: Swap positions — Output B first, Output A second. Record the verdict.
3. **Reconcile**: If both runs agree, the verdict is high confidence. If they disagree, the comparison is flagged as ambiguous.

This technique is automatic for all pairwise evaluators. No configuration needed.

## How it works

When you attach a pairwise evaluator to a run:

```python
with forkmark.run("my-workflow",
    evaluator_configs=[{"name": "pairwise_preference"}],
) as wf:
    out_a = wf.step("answer", model="gpt-4o-mini", messages=[...], call_fn=fn)
    out_b = wf.branch_step("answer", model="gpt-4o", messages=[...], call_fn=fn)
```

Forkmark:

1. Collects both branch outputs
2. Calls the LLM judge with Output A first, then with Output B first
3. Records both verdicts in `eval_results` on the comparison
4. Surfaces the result in the UI alongside the divergence score

## Built-in pairwise evaluators

### pairwise_preference

General-purpose comparison. Asks the judge: "Which output is better and why?"

### pairwise_conciseness

Compares brevity while maintaining completeness. Useful for summarization tasks.

### pairwise_expected_match

When you have a reference answer, compares which branch output is closer to it.

## Combining with human review

Pairwise evaluators provide automated pre-screening. The typical workflow:

1. Run a batch eval with `pairwise_preference` attached
2. Sort comparisons by divergence score (highest first)
3. Focus human review on cases where the evaluator is uncertain or divergence is high
4. Record structured decisions (choice, confidence, rationale)

The automated verdict and human verdict are stored independently — you can measure inter-rater agreement between your LLM judge and human reviewers over time.

## Configuring the judge model

The pairwise judge uses the model configured in `FM_JUDGE_MODEL` (default: `gpt-4o-mini`). For self-hosted models:

```bash
FM_JUDGE_MODEL=llama3-8b
FM_JUDGE_BASE_URL=http://localhost:11434/v1   # Ollama
```

Any OpenAI-compatible chat endpoint works.
