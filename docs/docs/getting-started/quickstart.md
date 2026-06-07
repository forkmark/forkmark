# Quickstart

Get Forkmark running and instrument your first A/B comparison in under 5 minutes.

## 1. Start the server

```bash
git clone https://github.com/forkmark/forkmark.git
cd forkmark
python start.py
```

The launcher auto-detects Docker (recommended) or falls back to Python direct mode. Forkmark starts on `http://localhost:7700`.

## 2. Create an API key

Open the Forkmark UI at `http://localhost:7700` and navigate to **API Keys**. Click **Create Key** to generate your first key (prefixed `fm_`).

Alternatively, bootstrap via CLI:

```bash
curl -X POST http://localhost:7700/api/keys \
  -H "Content-Type: application/json" \
  -d '{"label": "dev-key"}'
```

!!! note
    The first key can be created without authentication from localhost. Subsequent keys require an existing key.

## 3. Install the SDK

```bash
pip install forkmark

# With optional integrations:
pip install "forkmark[openai]"      # OpenAI wrapper
pip install "forkmark[anthropic]"   # Anthropic wrapper
pip install "forkmark[all]"         # Everything
```

## 4. Run your first comparison

```python
import forkmark

# Initialize the client
fp = forkmark.init(api_key="fm_your_key_here", workflow="support-triage")

# Define your LLM call function
def call_llm(model, messages, temperature=0.7):
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature
    )
    return resp.choices[0].message.content

# Run an A/B comparison
with forkmark.run("support-triage", input_data={"ticket": "My order hasn't arrived"}) as wf:
    # Branch A: baseline model
    out_a = wf.step(
        "classify",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Classify this support ticket: My order hasn't arrived"}],
        call_fn=call_llm,
    )

    # Branch B: challenger model
    out_b = wf.branch_step(
        "classify",
        model="gpt-4o",
        messages=[{"role": "user", "content": "Classify this support ticket: My order hasn't arrived"}],
        call_fn=call_llm,
    )

# A comparison is auto-created. Open the UI to review.
print("Done! Open http://localhost:7700 to compare outputs.")
```

## 5. Review and decide

Open the Forkmark UI. You'll see:

- **Side-by-side outputs** from both branches
- **Divergence score** showing how different the outputs are
- **Decision panel** where you record your verdict (A, B, both, or neither) with confidence and rationale

## Next steps

- [Run batch evaluations](../sdk/eval-runs.md) over test sets
- [Use drop-in integrations](../sdk/integrations.md) for OpenAI, Anthropic, and LangChain
- [Configure divergence scoring](configuration.md) for your use case
