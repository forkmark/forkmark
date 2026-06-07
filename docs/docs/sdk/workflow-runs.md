# Workflow Runs

A workflow run is a single execution of your AI pipeline with two branches (A and B). Forkmark compares their outputs and assigns a divergence score.

## Basic usage

```python
import forkmark

forkmark.init(api_key="fm_...", workflow="support-triage")

with forkmark.run("support-triage", input_data={"ticket": "Order delayed"}) as wf:
    # Branch A (baseline)
    out_a = wf.step(
        "classify",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Classify: Order delayed"}],
        call_fn=my_llm_call,
    )

    # Branch B (challenger)
    out_b = wf.branch_step(
        "classify",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Classify: Order delayed"}],
        call_fn=my_llm_call,
    )

# On exit, Forkmark creates a Comparison and scores divergence.
```

## Multi-step workflows

Workflows can have multiple sequential steps. Each step is logged independently:

```python
with forkmark.run("rag-pipeline", input_data={"query": "..."}) as wf:
    # Step 1: Retrieve
    context_a = wf.step("retrieve", model="gpt-4o-mini", messages=[...], call_fn=fn)
    context_b = wf.branch_step("retrieve", model="gpt-4o", messages=[...], call_fn=fn)

    # Step 2: Generate (using retrieved context)
    out_a = wf.step("generate", model="gpt-4o-mini", messages=[...], call_fn=fn)
    out_b = wf.branch_step("generate", model="gpt-4o", messages=[...], call_fn=fn)
```

Each step gets its own divergence score. The comparison view shows per-step divergence alongside the overall score.

## The call_fn pattern

The `call_fn` parameter accepts any callable that takes `(model, messages, temperature)` and returns a string:

```python
def my_llm_call(model, messages, temperature=0.7):
    resp = openai.ChatCompletion.create(
        model=model, messages=messages, temperature=temperature
    )
    return resp.choices[0].message.content
```

## Input data

The `input_data` dict is stored with the run and used as the prompt in DPO exports:

```python
with forkmark.run("qa", input_data={
    "question": "What is machine learning?",
    "context": "ML is a subset of AI...",
    "domain": "education",
}) as wf:
    ...
```

## Evaluator configs

Attach automated evaluators that run alongside human review:

```python
with forkmark.run("qa",
    input_data={"question": "..."},
    evaluator_configs=[
        {"name": "json_schema", "params": {"schema": my_schema}},
        {"name": "max_length", "params": {"max_length": 500}},
        {"name": "pairwise_preference"},
    ],
) as wf:
    ...
```

See [Built-in evaluators](../evaluators/built-in.md) for the full list.
