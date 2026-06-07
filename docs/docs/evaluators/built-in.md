# Built-in Evaluators

Forkmark includes three categories of automated evaluators that run alongside human review.

## Deterministic evaluators

These evaluators check structural properties of outputs without calling an LLM.

### json_schema

Validates that the output is valid JSON conforming to a JSON Schema.

```python
{"name": "json_schema", "params": {"schema": {
    "type": "object",
    "properties": {"category": {"type": "string"}, "confidence": {"type": "number"}},
    "required": ["category"]
}}}
```

### regex_match

Pattern matching with ReDoS protection (5-second timeout via the `regex` module).

```python
{"name": "regex_match", "params": {"pattern": r"^(positive|negative|neutral)$"}}
```

### exact_match

Checks if the output exactly matches an expected string.

```python
{"name": "exact_match", "params": {"expected": "approved"}}
```

### contains

Checks if the output contains a specific substring.

```python
{"name": "contains", "params": {"substring": "recommendation"}}
```

### max_length

Checks that output length is within bounds.

```python
{"name": "max_length", "params": {"max_length": 500}}
```

### latency_check

Checks that the LLM call completed within a time budget.

```python
{"name": "latency_check", "params": {"max_ms": 3000}}
```

## LLM-based evaluators

These evaluators use an LLM to assess output quality. They require `FM_OPENAI_API_KEY` and share an async httpx client with tenacity retry.

### faithfulness

RAG hallucination detection. Checks if the output is grounded in the provided context.

```python
{"name": "faithfulness", "params": {"context": "The company was founded in 2020..."}}
```

### relevance

RAG relevance scoring. Checks if the output addresses the original question.

```python
{"name": "relevance"}
```

### toxicity

Safety screening. Flags potentially harmful or toxic content.

```python
{"name": "toxicity"}
```

## Pairwise evaluators

Forkmark's differentiator. Pairwise evaluators compare two outputs head-to-head with **position debiasing** — each comparison runs twice with outputs swapped to eliminate order bias (the MT-Bench technique from Zheng et al., 2023).

### pairwise_preference

LLM-as-judge comparison. Asks the judge model which output is better and why.

```python
{"name": "pairwise_preference"}
```

### pairwise_conciseness

Compares which output is more concise while maintaining completeness.

```python
{"name": "pairwise_conciseness"}
```

### pairwise_expected_match

When an expected output is provided, compares which branch output is closer to it.

```python
{"name": "pairwise_expected_match", "params": {"expected": "The answer is 42."}}
```

## Combining evaluators

Attach multiple evaluators to a single run:

```python
with forkmark.run("qa",
    input_data={"question": "..."},
    evaluator_configs=[
        {"name": "json_schema", "params": {"schema": my_schema}},
        {"name": "max_length", "params": {"max_length": 500}},
        {"name": "faithfulness", "params": {"context": my_context}},
        {"name": "pairwise_preference"},
    ],
) as wf:
    ...
```

Results appear in the comparison view alongside the divergence score and human decision.
