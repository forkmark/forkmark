# SDK Integrations

Forkmark provides drop-in wrappers for popular LLM providers. Each integration auto-logs prompts, outputs, latency, tokens, and cost without modifying your existing code.

## OpenAI

```bash
pip install "forkmark[openai]"
```

### Sync

```python
from forkmark.integrations.openai_wrapper import ForkmarkOpenAI
import forkmark

fp = forkmark.init(api_key="fm_...", workflow="my-workflow")

with forkmark.run("my-workflow") as run:
    client_a = ForkmarkOpenAI(
        openai_api_key="sk-...", fm_client=fp,
        workflow_ctx=run, branch_type="A", step_name="answer"
    )
    client_b = ForkmarkOpenAI(
        openai_api_key="sk-...", fm_client=fp,
        workflow_ctx=run, branch_type="B", step_name="answer"
    )

    resp_a = client_a.chat.completions.create(model="gpt-4o-mini", messages=[...])
    resp_b = client_b.chat.completions.create(model="gpt-4o", messages=[...])
```

### Async

```python
resp = await client_a.chat.completions.acreate(model="gpt-4o-mini", messages=[...])
```

### Streaming

```python
# Sync streaming
stream = client_a.chat.completions.create(model="gpt-4o-mini", messages=[...], stream=True)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
# Forkmark logs the full call on stream completion

# Async streaming
async with client_a.chat.completions.acreate(model="gpt-4o", messages=[...], stream=True) as stream:
    async for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="")
```

## Anthropic

```bash
pip install "forkmark[anthropic]"
```

### Sync

```python
from forkmark.integrations.anthropic_wrapper import ForkmarkAnthropic
import forkmark

fp = forkmark.init(api_key="fm_...", workflow="my-workflow")

with forkmark.run("my-workflow") as run:
    client_a = ForkmarkAnthropic(
        anthropic_api_key="sk-ant-...", fm_client=fp,
        workflow_ctx=run, branch_type="A"
    )

    resp = client_a.messages.create(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=1024,
        system="You are a helpful assistant.",
    )
```

### Async

```python
resp = await client_a.messages.acreate(model="claude-sonnet-4-20250514", messages=[...], max_tokens=1024)
```

### Streaming

```python
# Sync streaming
stream = client_a.messages.create(model="claude-sonnet-4-20250514", messages=[...], max_tokens=1024, stream=True)
for event in stream:
    if hasattr(event, 'delta') and hasattr(event.delta, 'text'):
        print(event.delta.text, end="")

# Async streaming
async with client_a.messages.acreate(..., stream=True) as stream:
    async for event in stream:
        ...
```

## LangChain

```bash
pip install "forkmark[langchain]"
```

```python
from forkmark.integrations.langchain_callback import ForkmarkCallbackHandler
import forkmark

fp = forkmark.init(api_key="fm_...", workflow="my-chain")

with forkmark.run("my-chain") as run:
    handler = ForkmarkCallbackHandler(
        fm_client=fp, run_id=run.run_id, branch_id=run.branch_a_id
    )

    # Use with any LangChain LLM
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[handler])
    chain = prompt | llm
    result = chain.invoke({"input": "..."})
```

The callback handler captures the actual prompt text from `on_llm_start` and reads temperature from the serialized LLM config.

## Attach pattern

If you prefer to create the wrapper before the run starts, use `.attach()`:

```python
client_a = ForkmarkOpenAI(openai_api_key="sk-...", fm_client=fp, branch_type="A")

with forkmark.run("my-workflow") as run:
    client_a.attach(run)
    resp = client_a.chat.completions.create(...)
```

!!! warning
    If you call the wrapper without attaching a workflow context, a warning is logged and the LLM call proceeds but is not recorded in Forkmark.
