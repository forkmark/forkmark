# SDK Overview

The Forkmark Python SDK instruments your AI workflows in 3 lines. It ships telemetry (prompts, outputs, latency, cost, tokens) to the Forkmark server, where comparisons are scored and presented for human review.

## Installation

```bash
pip install forkmark
```

## Initialize

```python
import forkmark

fp = forkmark.init(
    api_key="fm_your_key_here",
    base_url="http://localhost:7700",   # default
    workflow="my-workflow",              # default workflow name
)
```

After `init()`, the global client is available via `forkmark._default` and convenience functions (`forkmark.run()`, `forkmark.eval_run()`).

## Core concepts

### Workflow run

A single execution of your AI pipeline with two branches (A and B). Each branch runs the same steps with different configurations (model, temperature, prompt).

```python
with forkmark.run("my-workflow", input_data={"query": "..."}) as wf:
    out_a = wf.step("generate", model="gpt-4o-mini", messages=[...], call_fn=fn)
    out_b = wf.branch_step("generate", model="gpt-4o", messages=[...], call_fn=fn)
```

See [Workflow runs](workflow-runs.md) for details.

### Eval run

A batch evaluation over a list of test inputs. Each input runs through both branches, producing comparisons for review.

```python
with forkmark.eval_run(
    name="GPT-4o-mini vs GPT-4o — Q3 tickets",
    workflow="support-triage",
    branch_a={"label": "GPT-4o-mini", "model_id": "gpt-4o-mini", "temperature": 0.3},
    branch_b={"label": "GPT-4o", "model_id": "gpt-4o", "temperature": 0.3},
    inputs=test_cases,
) as er:
    for case in er:
        out_a = case.step("classify", model="gpt-4o-mini", messages=[...], call_fn=fn)
        out_b = case.branch_step("classify", model="gpt-4o", messages=[...], call_fn=fn)
```

See [Eval runs](eval-runs.md) for details.

### Integrations

Drop-in wrappers that auto-log LLM calls without modifying your existing code:

```python
# OpenAI
from forkmark.integrations.openai_wrapper import ForkmarkOpenAI
client = ForkmarkOpenAI(openai_api_key="sk-...", fm_client=fp, branch_type="A")

# Anthropic
from forkmark.integrations.anthropic_wrapper import ForkmarkAnthropic
client = ForkmarkAnthropic(anthropic_api_key="sk-ant-...", fm_client=fp, branch_type="B")

# LangChain
from forkmark.integrations.langchain_callback import ForkmarkCallbackHandler
handler = ForkmarkCallbackHandler(fm_client=fp, run_id="...", branch_id="...")
```

See [Integrations](integrations.md) for details.

## Version

```python
import forkmark
print(forkmark.__version__)  # "0.1.2"
```
