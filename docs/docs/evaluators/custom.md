# Custom Evaluators

Forkmark includes a registry system for adding your own evaluators.

## Creating a custom evaluator

Register a function that takes the evaluator context and returns a result dict:

```python
from core.evaluators import register_evaluator

@register_evaluator("domain_accuracy")
def domain_accuracy_evaluator(output_text: str, params: dict, **kwargs) -> dict:
    """Check if the output contains domain-specific terminology."""
    required_terms = params.get("required_terms", [])
    found = [t for t in required_terms if t.lower() in output_text.lower()]
    score = len(found) / len(required_terms) if required_terms else 1.0

    return {
        "pass": score >= params.get("threshold", 0.5),
        "score": score,
        "details": {
            "found_terms": found,
            "missing_terms": [t for t in required_terms if t not in found],
        },
    }
```

## Using custom evaluators

Once registered, use them like any built-in evaluator:

```python
with forkmark.run("medical-qa",
    evaluator_configs=[
        {
            "name": "domain_accuracy",
            "params": {
                "required_terms": ["diagnosis", "treatment", "prognosis"],
                "threshold": 0.66,
            },
        },
    ],
) as wf:
    ...
```

## Evaluator return format

Your evaluator function should return a dict with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pass` | bool | Yes | Whether the output passed the evaluation |
| `score` | float | No | Numeric score (0.0–1.0) |
| `details` | dict | No | Arbitrary metadata shown in the UI |

## Registration at startup

Register evaluators before the FastAPI app starts. A common pattern is to place them in a `custom_evaluators.py` module and import it in your startup:

```python
# custom_evaluators.py
from core.evaluators import register_evaluator

@register_evaluator("my_eval")
def my_eval(output_text, params, **kwargs):
    ...

# In your startup or main.py
import custom_evaluators  # registers on import
```
