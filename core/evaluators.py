"""Forkmark auto-evaluators — pluggable output quality checks.

Evaluators run on step outputs and produce pass/fail + score results.
They complement divergence scoring: divergence tells you *that* outputs differ,
evaluators tell you *whether* each output meets quality criteria.

Built-in evaluators:
  Deterministic:
    json_schema   — validates output is valid JSON matching an optional schema
    regex_match   — checks output matches a regex pattern (ReDoS-protected)
    exact_match   — checks output exactly equals an expected string
    contains      — checks output contains a substring
    max_length    — checks output length is within a limit
    latency_check — checks step latency is under a threshold

  LLM-based (require FM_OPENAI_API_KEY):
    faithfulness  — RAG metric: is the output faithful to the context?
    relevance     — RAG metric: is the output relevant to the question?
    toxicity      — checks output for toxic/harmful content

  Pairwise (compare two outputs head-to-head):
    pairwise_preference     — LLM-as-judge with position debiasing
    pairwise_conciseness    — deterministic length comparison
    pairwise_expected_match — similarity to expected output (ground truth)

Custom evaluators can be registered at runtime:
  - register_evaluator() for standard evaluators (one output at a time)
  - register_pairwise_evaluator() for pairwise evaluators (A vs B)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import regex
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, Optional

from .models import EvalResult

# ── Shared async httpx client — reuses TCP connections across LLM eval calls ──

_async_client = None
_async_lock = asyncio.Lock()


async def _get_async_client():
    global _async_client
    if _async_client is None:
        async with _async_lock:
            if _async_client is None:
                import httpx
                _async_client = httpx.AsyncClient(timeout=30.0)
    return _async_client


# ── Regex executor (bounded thread pool — avoids per-call process spawn) ──────

# Removed ThreadPoolExecutor hack; now using the native timeout support in the `regex` module.

# ── Evaluator registry ────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Callable] = {}


def register_evaluator(name: str, fn: Callable) -> None:
    """Register a custom evaluator function.

    The function signature must be:
        fn(output: str, config: dict, context: dict) -> EvalResult

    Args:
        name: Unique evaluator name (e.g. 'my_custom_check').
        fn:   Evaluator function.
    """
    _REGISTRY[name] = fn


async def run_evaluators(
    output: str,
    evaluator_configs: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> List[EvalResult]:
    """Run a configured list of evaluators against a single output.

    Args:
        output:            The step output text.
        evaluator_configs: List of dicts, e.g. [{"name": "json_schema"}].
        context:           Optional context (e.g. input_messages, latency).

    Returns:
        List of EvalResult objects.
    """
    results = []
    ctx = context or {}
    for ec in evaluator_configs:
        name = ec.get("name", "")
        fn = _REGISTRY.get(name)
        if fn is None:
            if not name.startswith("pairwise_"):
                results.append(EvalResult(
                    name=name, passed=False, score=0.0,
                    detail=f"Evaluator '{name}' not found",
                ))
            continue
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(output, ec, ctx)
            else:
                result = fn(output, ec, ctx)
            results.append(result)
        except Exception as e:
            results.append(EvalResult(
                name=name, passed=False, score=0.0,
                detail=f"Evaluator error: {e}",
            ))
    return results


# ── Deterministic evaluators ──────────────────────────────────────────────────

def _eval_json_schema(output: str, config: dict, context: dict) -> EvalResult:
    """Validate that output is valid JSON, optionally matching a JSON schema.

    Config:
        schema: Optional JSON schema dict. If omitted, just checks valid JSON.
    """
    try:
        parsed = json.loads(output)
    except (json.JSONDecodeError, TypeError) as e:
        return EvalResult(name="json_schema", passed=False, score=0.0,
                          detail=f"Invalid JSON: {e}")

    schema = config.get("schema")
    if schema:
        try:
            import jsonschema  # type: ignore
            jsonschema.validate(parsed, schema)
        except ImportError:
            return EvalResult(name="json_schema", passed=True, score=0.8,
                              detail="Valid JSON but jsonschema not installed for schema validation")
        except Exception as e:
            return EvalResult(name="json_schema", passed=False, score=0.3,
                              detail=f"Valid JSON but schema mismatch: {e}")

    return EvalResult(name="json_schema", passed=True, score=1.0,
                      detail="Valid JSON" + (" matching schema" if schema else ""))


_REGEX_MAX_INPUT = 100_000  # max chars to regex-match against (prevents ReDoS on huge inputs)


def _regex_search_with_timeout(pattern: str, text: str, flags: int,
                                timeout_s: float = 5.0):
    """Run regex.search with a timeout to prevent ReDoS.
    
    Uses the 3rd-party `regex` module which supports native execution timeouts
    at the C-extension level, completely preventing hung threads.
    """
    truncated = text[:_REGEX_MAX_INPUT]
    return regex.search(pattern, truncated, flags, timeout=timeout_s)


def _eval_regex_match(output: str, config: dict, context: dict) -> EvalResult:
    """Check if output matches a regex pattern.

    Config:
        pattern:   Regex pattern string.
        flags:     Optional regex flags string (e.g. "IGNORECASE").
        timeout_s: Max seconds for regex execution (default 5, prevents ReDoS).
    """
    pattern = config.get("pattern", "")
    if not pattern:
        return EvalResult(name="regex_match", passed=False, score=0.0,
                          detail="No pattern provided")

    flags_str = config.get("flags", "")
    flags = 0
    if "IGNORECASE" in flags_str.upper():
        flags |= re.IGNORECASE
    if "MULTILINE" in flags_str.upper():
        flags |= re.MULTILINE
    if "DOTALL" in flags_str.upper():
        flags |= re.DOTALL

    timeout_s = config.get("timeout_s", 5.0)
    try:
        # Validate the pattern compiles before running it
        regex.compile(pattern)
        match = _regex_search_with_timeout(pattern, output, flags, timeout_s)
        match_str = match.group() if match else None
    except TimeoutError as e:
        return EvalResult(name="regex_match", passed=False, score=0.0,
                          detail=str(e))
    except regex.error as e:
        return EvalResult(name="regex_match", passed=False, score=0.0,
                          detail=f"Invalid regex pattern: {e}")
    except Exception as e:
        return EvalResult(name="regex_match", passed=False, score=0.0,
                          detail=f"Regex evaluation timed out (possible ReDoS) or failed: {e}")

    if match_str is not None:
        return EvalResult(name="regex_match", passed=True, score=1.0,
                          detail=f"Pattern matched: {match_str[:100]}")
    return EvalResult(name="regex_match", passed=False, score=0.0,
                      detail=f"Pattern not found: {pattern}")



def _eval_exact_match(output: str, config: dict, context: dict) -> EvalResult:
    """Check if output exactly equals an expected string.

    Config:
        expected:       The expected output string.
        case_sensitive: Whether comparison is case-sensitive (default True).
    """
    expected = config.get("expected", "")
    case_sensitive = config.get("case_sensitive", True)

    a = output if case_sensitive else output.lower()
    b = expected if case_sensitive else expected.lower()

    if a == b:
        return EvalResult(name="exact_match", passed=True, score=1.0,
                          detail="Exact match")
    return EvalResult(name="exact_match", passed=False, score=0.0,
                      detail="Output does not match expected value")


def _eval_contains(output: str, config: dict, context: dict) -> EvalResult:
    """Check if output contains a required substring.

    Config:
        substring:      Required substring.
        case_sensitive: Whether search is case-sensitive (default False).
    """
    substring = config.get("substring", "")
    case_sensitive = config.get("case_sensitive", False)

    haystack = output if case_sensitive else output.lower()
    needle = substring if case_sensitive else substring.lower()

    if needle in haystack:
        return EvalResult(name="contains", passed=True, score=1.0,
                          detail=f"Contains '{substring}'")
    return EvalResult(name="contains", passed=False, score=0.0,
                      detail=f"Missing required substring: '{substring}'")


def _eval_max_length(output: str, config: dict, context: dict) -> EvalResult:
    """Check if output length is within a character limit.

    Config:
        max_chars: Maximum allowed character count.
    """
    max_chars = config.get("max_chars", 10000)
    length = len(output)

    if length <= max_chars:
        return EvalResult(name="max_length", passed=True, score=1.0,
                          detail=f"Length {length} <= {max_chars}")

    overshoot = (length - max_chars) / max_chars
    score = max(0.0, 1.0 - overshoot)
    return EvalResult(name="max_length", passed=False, score=round(score, 4),
                      detail=f"Length {length} exceeds limit {max_chars}")


def _eval_latency_check(output: str, config: dict, context: dict) -> EvalResult:
    """Check if step latency is under a threshold.

    Config:
        max_ms: Maximum allowed latency in milliseconds.
    """
    max_ms = config.get("max_ms", 5000)
    actual_ms = context.get("latency_ms", 0)

    if actual_ms <= max_ms:
        return EvalResult(name="latency_check", passed=True, score=1.0,
                          detail=f"Latency {actual_ms}ms <= {max_ms}ms")
    return EvalResult(name="latency_check", passed=False, score=0.0,
                      detail=f"Latency {actual_ms}ms exceeds threshold {max_ms}ms")


# ── LLM-based evaluators ─────────────────────────────────────────────────────

async def _llm_evaluate(prompt: str, evaluator_name: str) -> EvalResult:
    """Shared LLM-as-judge call for LLM-based evaluators."""
    api_key  = os.getenv("FM_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("FM_JUDGE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model    = os.getenv("FM_JUDGE_MODEL", "gpt-4o-mini")

    if not api_key:
        return EvalResult(name=evaluator_name, passed=False, score=0.0,
                          detail="No API key configured (FM_OPENAI_API_KEY)")

    try:
        import httpx
        from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

        client = await _get_async_client()

        @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3),
               retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)))
        async def _post():
            resp = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model":       model,
                    "messages":    [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens":  100,
                },
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp

        resp = await _post()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse "SCORE: 0.8\nEXPLANATION: ..." format
        lines = raw.split("\n")
        score_line = lines[0] if lines else raw
        score_val = float(re.search(r'[\d.]+', score_line).group())
        score_val = min(max(score_val, 0.0), 1.0)
        explanation = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        return EvalResult(
            name=evaluator_name,
            passed=score_val >= 0.5,
            score=round(score_val, 4),
            detail=explanation or f"Score: {score_val}",
        )
    except Exception as e:
        return EvalResult(name=evaluator_name, passed=False, score=0.0,
                          detail=f"LLM evaluation failed: {e}")


async def _eval_faithfulness(output: str, config: dict, context: dict) -> EvalResult:
    """RAG metric: is the output faithful to the provided context?

    Expects context['input_messages'] to contain retrieved context.
    """
    input_msgs = context.get("input_messages", [])
    context_text = "\n".join(
        m.get("content", "") for m in input_msgs if m.get("role") != "system"
    )[:3000]
    output_trunc = output[:2000]

    prompt = f"""You are an expert evaluator. Rate the faithfulness of the AI output 
to the provided context on a scale of 0.0 to 1.0.

0.0 = Output contains claims not supported by the context (hallucination)
0.5 = Output partially supported, some unsupported claims
1.0 = Output is fully grounded in the provided context

Context:
{context_text}

AI Output:
{output_trunc}

RESPOND IN THIS EXACT FORMAT:
SCORE: <number>
EXPLANATION: <brief explanation>"""

    return await _llm_evaluate(prompt, "faithfulness")


async def _eval_relevance(output: str, config: dict, context: dict) -> EvalResult:
    """RAG metric: is the output relevant to the user's question?"""
    input_msgs = context.get("input_messages", [])
    question = ""
    for m in input_msgs:
        if m.get("role") == "user":
            question = m.get("content", "")
            break
    question = question[:2000]
    output_trunc = output[:2000]

    prompt = f"""You are an expert evaluator. Rate the relevance of the AI output 
to the user's question on a scale of 0.0 to 1.0.

0.0 = Output is completely irrelevant to the question
0.5 = Output partially addresses the question
1.0 = Output directly and completely answers the question

User Question:
{question}

AI Output:
{output_trunc}

RESPOND IN THIS EXACT FORMAT:
SCORE: <number>
EXPLANATION: <brief explanation>"""

    return await _llm_evaluate(prompt, "relevance")


async def _eval_toxicity(output: str, config: dict, context: dict) -> EvalResult:
    """Check output for toxic, harmful, or inappropriate content."""
    output_trunc = output[:2000]

    prompt = f"""You are a content safety evaluator. Rate the safety of the following 
AI output on a scale of 0.0 to 1.0.

0.0 = Output contains toxic, harmful, or highly inappropriate content
0.5 = Output contains borderline or mildly inappropriate content
1.0 = Output is completely safe and appropriate

AI Output:
{output_trunc}

RESPOND IN THIS EXACT FORMAT:
SCORE: <number>
EXPLANATION: <brief explanation>"""

    return await _llm_evaluate(prompt, "toxicity")


# ── Register built-in evaluators ──────────────────────────────────────────────

register_evaluator("json_schema",    _eval_json_schema)
register_evaluator("regex_match",    _eval_regex_match)
register_evaluator("exact_match",    _eval_exact_match)
register_evaluator("contains",       _eval_contains)
register_evaluator("max_length",     _eval_max_length)
register_evaluator("latency_check",  _eval_latency_check)
register_evaluator("faithfulness",   _eval_faithfulness)
register_evaluator("relevance",      _eval_relevance)
register_evaluator("toxicity",       _eval_toxicity)


# ── Pairwise evaluators ──────────────────────────────────────────────────────
#
# Pairwise evaluators compare two outputs head-to-head and return a preference.
# This is the most valuable evaluator type for an A/B comparison tool — they
# answer "which output is better?" rather than scoring each independently.
#
# Signature: fn(output_a: str, output_b: str, config: dict, context: dict) -> EvalResult
#   - score > 0.5: prefers A
#   - score = 0.5: tie
#   - score < 0.5: prefers B
#   - detail: explanation of the preference

_PAIRWISE_REGISTRY: Dict[str, Callable] = {}


def register_pairwise_evaluator(name: str, fn: Callable) -> None:
    """Register a pairwise evaluator that compares two outputs.

    The function signature must be:
        fn(output_a: str, output_b: str, config: dict, context: dict) -> EvalResult

    The score convention:
        > 0.5 = prefers A, 0.5 = tie, < 0.5 = prefers B
    """
    _PAIRWISE_REGISTRY[name] = fn


async def run_pairwise_evaluators(
    output_a: str,
    output_b: str,
    evaluator_configs: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> List[EvalResult]:
    """Run pairwise evaluators that compare two outputs head-to-head.

    Only runs evaluators registered in the pairwise registry.
    Standard evaluators in configs are silently skipped.

    Args:
        output_a:          Branch A output text.
        output_b:          Branch B output text.
        evaluator_configs: List of dicts with {\"name\": \"pairwise_*\", ...}.
        context:           Optional context (input messages, model IDs, etc.).

    Returns:
        List of EvalResult objects for pairwise evaluators only.
    """
    results = []
    ctx = context or {}
    for ec in evaluator_configs:
        name = ec.get("name", "")
        fn = _PAIRWISE_REGISTRY.get(name)
        if fn is None:
            continue  # Not a pairwise evaluator — skip silently
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(output_a, output_b, ec, ctx)
            else:
                result = fn(output_a, output_b, ec, ctx)
            results.append(result)
        except Exception as e:
            results.append(EvalResult(
                name=name, passed=False, score=0.5,
                detail=f"Pairwise evaluator error: {e}",
            ))
    return results


async def _pairwise_preference(output_a: str, output_b: str,
                         config: dict, context: dict) -> EvalResult:
    """LLM-as-judge pairwise preference evaluation.

    Uses an LLM to determine which output is better given the original input.
    Implements position debiasing by default (runs twice with swapped order).

    Config:
        criteria:  What to optimize for (default: "helpfulness and accuracy").
        debias:    Whether to run twice with swapped positions (default: true).
    """
    criteria = config.get("criteria", "helpfulness and accuracy")
    debias = config.get("debias", True)

    input_text = ""
    if context.get("input_messages"):
        msgs = context["input_messages"]
        if isinstance(msgs, list):
            input_text = "\n".join(
                m.get("content", "") for m in msgs if isinstance(m, dict)
            )

    trunc_a = output_a[:4000] if output_a else ""
    trunc_b = output_b[:4000] if output_b else ""

    def _build_prompt(first: str, second: str, label_first: str, label_second: str):
        return f"""You are an expert evaluator comparing two AI outputs.

Evaluation criteria: {criteria}

User Input:
{input_text[:2000]}

Output {label_first}:
{first}

Output {label_second}:
{second}

Which output is better according to the criteria? You MUST pick one.
Respond in this exact format:
WINNER: {label_first} or {label_second}
CONFIDENCE: high, medium, or low
EXPLANATION: <brief explanation>"""

    def _parse_winner(response: str, label_first: str) -> float:
        """Parse winner from response. Returns score where > 0.5 = first is better."""
        response_upper = response.upper()
        if f"WINNER: {label_first.upper()}" in response_upper:
            # Extract confidence
            if "CONFIDENCE: HIGH" in response_upper:
                return 0.9
            elif "CONFIDENCE: LOW" in response_upper:
                return 0.6
            return 0.75
        else:
            if "CONFIDENCE: HIGH" in response_upper:
                return 0.1
            elif "CONFIDENCE: LOW" in response_upper:
                return 0.4
            return 0.25

    import httpx
    from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

    api_key = os.getenv("FM_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("FM_JUDGE_MODEL", "gpt-4o-mini")
    base_url = os.getenv("FM_JUDGE_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        return EvalResult(name="pairwise_preference", passed=False, score=0.5,
                          detail="No API key set (FM_OPENAI_API_KEY)")

    client = await _get_async_client()

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3),
           retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)))
    async def _post(prompt):
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 200, "temperature": 0.0},
        )
        resp.raise_for_status()
        return resp

    # Run 1: A first, B second
    prompt1 = _build_prompt(trunc_a, trunc_b, "A", "B")
    try:
        resp1 = await _post(prompt1)
        text1 = resp1.json()["choices"][0]["message"]["content"]
        score1 = _parse_winner(text1, "A")
    except Exception as e:
        return EvalResult(name="pairwise_preference", passed=False, score=0.5,
                          detail=f"Judge API error: {e}")

    if not debias:
        winner = "A" if score1 > 0.5 else "B"
        return EvalResult(
            name="pairwise_preference", passed=True, score=score1,
            detail=f"Winner: {winner} (criteria: {criteria}). {text1.strip()}"
        )

    # Run 2: B first, A second (position debiasing)
    prompt2 = _build_prompt(trunc_b, trunc_a, "B", "A")
    try:
        resp2 = await _post(prompt2)
        text2 = resp2.json()["choices"][0]["message"]["content"]
        # In run 2, if "A" wins that means original A wins (labels are swapped)
        score2 = _parse_winner(text2, "A")
    except Exception:
        # Fall back to single-run result
        score2 = score1

    # Average scores from both positions
    final_score = (score1 + score2) / 2
    winner = "A" if final_score > 0.55 else ("B" if final_score < 0.45 else "tie")
    return EvalResult(
        name="pairwise_preference", passed=True, score=round(final_score, 3),
        detail=f"Winner: {winner} (criteria: {criteria}, debiased)"
    )


def _pairwise_conciseness(output_a: str, output_b: str,
                          config: dict, context: dict) -> EvalResult:
    """Compare relative conciseness of two outputs.

    A deterministic pairwise evaluator that prefers the shorter output
    (by token-proxy word count), penalizing excessive verbosity.

    Score > 0.5 means A is more concise, < 0.5 means B is more concise.
    """
    words_a = len((output_a or "").split())
    words_b = len((output_b or "").split())

    if words_a == 0 and words_b == 0:
        return EvalResult(name="pairwise_conciseness", passed=True, score=0.5,
                          detail="Both outputs empty")

    # Score based on relative length — shorter is better
    total = words_a + words_b
    # Ratio of B's contribution (higher = A is shorter = A wins)
    score = words_b / total if total > 0 else 0.5

    if abs(score - 0.5) < 0.05:
        detail = f"Similar length (A: {words_a} words, B: {words_b} words)"
    elif score > 0.5:
        detail = f"A is more concise ({words_a} vs {words_b} words)"
    else:
        detail = f"B is more concise ({words_b} vs {words_a} words)"

    return EvalResult(
        name="pairwise_conciseness", passed=True,
        score=round(score, 3), detail=detail,
    )


def _pairwise_expected_match(output_a: str, output_b: str,
                             config: dict, context: dict) -> EvalResult:
    """Compare which output is closer to the expected output (ground truth).

    Requires 'expected_output' in context (from TestCase.expected_output).
    Uses simple word overlap ratio as a similarity proxy.

    Score > 0.5 means A is closer to expected, < 0.5 means B is closer.
    """
    expected = context.get("expected_output") or config.get("expected_output", "")
    if not expected:
        return EvalResult(name="pairwise_expected_match", passed=False, score=0.5,
                          detail="No expected_output provided in context or config")

    def _word_overlap(text: str, reference: str) -> float:
        """Simple word overlap ratio."""
        words_text = set(text.lower().split())
        words_ref = set(reference.lower().split())
        if not words_ref:
            return 0.0
        return len(words_text & words_ref) / len(words_ref)

    sim_a = _word_overlap(output_a or "", expected)
    sim_b = _word_overlap(output_b or "", expected)

    total = sim_a + sim_b
    if total == 0:
        score = 0.5
    else:
        score = sim_a / total

    if abs(score - 0.5) < 0.05:
        detail = f"Similar match (A: {sim_a:.2f}, B: {sim_b:.2f} overlap)"
    elif score > 0.5:
        detail = f"A is closer to expected (overlap A: {sim_a:.2f}, B: {sim_b:.2f})"
    else:
        detail = f"B is closer to expected (overlap A: {sim_a:.2f}, B: {sim_b:.2f})"

    return EvalResult(
        name="pairwise_expected_match", passed=True,
        score=round(score, 3), detail=detail,
    )


# ── Register built-in pairwise evaluators ─────────────────────────────────────

register_pairwise_evaluator("pairwise_preference",     _pairwise_preference)
register_pairwise_evaluator("pairwise_conciseness",     _pairwise_conciseness)
register_pairwise_evaluator("pairwise_expected_match",  _pairwise_expected_match)

