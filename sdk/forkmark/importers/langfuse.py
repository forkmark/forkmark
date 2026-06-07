"""Import Langfuse generations into Forkmark as A/B comparisons.

The idea: if you already log your LLM calls to Langfuse, you've recorded the
same eval inputs run through different models. This importer pulls those logged
generations and pairs them — same input, model A vs model B — into Forkmark
comparisons you can review and export as DPO data.

Two data sources (see `load_from_file` / `fetch_from_api`):
  - a Langfuse export file (JSON array, {"data": [...]}, or .jsonl)
  - the Langfuse public API (v1 `/api/public/observations`, works self-hosted)

Pairing strategy (v1): "match by identical input". Generations are grouped by
their (canonicalised) input; within each group the output from `model_a` becomes
branch A and the output from `model_b` becomes branch B. If the two model names
aren't given they're auto-detected as the two most common models in the data.

The parser is deliberately tolerant of field-name differences between Langfuse
API versions (`model` vs `providedModelName`) and of input/output being either
JSON strings or already-parsed objects.
"""
from __future__ import annotations

import json
import os
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Field coercion helpers ────────────────────────────────────────────────────

def _coerce(value: Any) -> Any:
    """If value is a JSON string, parse it; otherwise return as-is."""
    if isinstance(value, str):
        s = value.strip()
        if s and s[0] in "[{\"":
            try:
                return json.loads(s)
            except (ValueError, TypeError):
                return value
    return value


def _to_messages(input_value: Any) -> Tuple[List[dict], str]:
    """Normalise a Langfuse `input` into (messages, input_text).

    Handles: {"messages": [...]}, a bare messages list, {"prompt"/"input": "..."},
    or a plain string.
    """
    v = _coerce(input_value)
    messages: List[dict]
    if isinstance(v, dict) and isinstance(v.get("messages"), list):
        messages = [m for m in v["messages"] if isinstance(m, dict)]
    elif isinstance(v, list) and v and isinstance(v[0], dict) and "role" in v[0]:
        messages = v
    elif isinstance(v, dict):
        text = v.get("prompt") or v.get("input") or v.get("content") or json.dumps(v, sort_keys=True)
        messages = [{"role": "user", "content": str(text)}]
    else:
        messages = [{"role": "user", "content": _stringify(v)}]

    # input_text = last user message, else a stringification of the whole input
    user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
    input_text = str(user_msgs[-1]) if user_msgs else _stringify(v)
    return messages, input_text


def _to_text(output_value: Any) -> str:
    """Normalise a Langfuse `output` into assistant text."""
    v = _coerce(output_value)
    if isinstance(v, dict):
        return str(v.get("content") or v.get("text") or v.get("output") or json.dumps(v, sort_keys=True))
    if isinstance(v, list) and v and isinstance(v[-1], dict):
        return str(v[-1].get("content") or json.dumps(v[-1]))
    return _stringify(v)


def _stringify(v: Any) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(v)


def _input_key(input_value: Any) -> str:
    """Canonical key so the same input from two models groups together."""
    return _stringify(_coerce(input_value))


def _model_of(obs: dict) -> Optional[str]:
    return (obs.get("model") or obs.get("providedModelName")
            or (obs.get("modelParameters") or {}).get("model"))


def _temp_of(obs: dict) -> float:
    mp = obs.get("modelParameters") or {}
    try:
        return float(mp.get("temperature", 0.7))
    except (TypeError, ValueError):
        return 0.7


# ── Normalised record ─────────────────────────────────────────────────────────

@dataclass
class _Gen:
    id: str
    model: Optional[str]
    input_key: str
    messages: List[dict]
    input_text: str
    output: str
    temperature: float
    label: str
    metadata: dict = field(default_factory=dict)


def normalize_observation(obs: dict) -> Optional[_Gen]:
    """Convert one Langfuse observation into a `_Gen`, or None if unusable.

    Skips non-generation observations and rows missing input or output.
    """
    otype = (obs.get("type") or "GENERATION")
    if str(otype).upper() != "GENERATION":
        return None
    if obs.get("input") is None or obs.get("output") is None:
        return None

    messages, input_text = _to_messages(obs.get("input"))
    output = _to_text(obs.get("output"))
    if not output.strip():
        return None

    metadata = obs.get("metadata") or {}
    label = (metadata.get("label") if isinstance(metadata, dict) else None) \
        or obs.get("name") or (input_text[:48] if input_text else obs.get("id", ""))

    return _Gen(
        id=str(obs.get("id", "")),
        model=_model_of(obs),
        input_key=_input_key(obs.get("input")),
        messages=messages,
        input_text=input_text,
        output=output,
        temperature=_temp_of(obs),
        label=str(label),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


# ── Pairing ───────────────────────────────────────────────────────────────────

@dataclass
class Pair:
    input_data: dict
    messages: List[dict]
    output_a: str
    output_b: str
    label: str


def detect_models(gens: List[_Gen]) -> List[str]:
    """Most common model names, descending by frequency."""
    counts = Counter(g.model for g in gens if g.model)
    return [m for m, _ in counts.most_common()]


def pair_by_input(observations: List[dict],
                  model_a: Optional[str] = None,
                  model_b: Optional[str] = None) -> Tuple[List[Pair], Optional[str], Optional[str]]:
    """Pair generations by identical input across two models.

    Returns (pairs, model_a, model_b). model_a/model_b are the (possibly
    auto-detected) model names actually used for branches A and B.
    """
    gens = [g for g in (normalize_observation(o) for o in observations) if g is not None]

    if not model_a or not model_b:
        common = detect_models(gens)
        if not model_a:
            model_a = common[0] if common else None
        if not model_b:
            model_b = next((m for m in common if m != model_a), None)

    if not model_a or not model_b:
        return [], model_a, model_b

    # Preserve first-seen order of inputs for stable, reproducible output.
    groups: "OrderedDict[str, List[_Gen]]" = OrderedDict()
    for g in gens:
        groups.setdefault(g.input_key, []).append(g)

    pairs: List[Pair] = []
    for items in groups.values():
        a = next((x for x in items if x.model == model_a), None)
        b = next((x for x in items if x.model == model_b), None)
        if a and b and a.output and b.output:
            pairs.append(Pair(
                input_data={"prompt": a.input_text, "messages": a.messages},
                messages=a.messages,
                output_a=a.output,
                output_b=b.output,
                label=a.label,
            ))
    return pairs, model_a, model_b


# ── Data sources ──────────────────────────────────────────────────────────────

def load_from_file(path: str) -> List[dict]:
    """Load Langfuse observations from a JSON array, {"data": [...]}, or .jsonl."""
    if path.endswith(".jsonl"):
        out = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data, list):
        return data
    raise ValueError(
        f"{path}: expected a JSON array, an object with a 'data' array, or .jsonl"
    )


def fetch_from_api(host: str, public_key: str, secret_key: str, *,
                   from_time: Optional[str] = None, to_time: Optional[str] = None,
                   name: Optional[str] = None, limit: int = 1000,
                   page_size: int = 100) -> List[dict]:
    """Fetch GENERATION observations from the Langfuse public API (v1).

    Uses HTTP Basic auth (public key = username, secret key = password) against
    `GET {host}/api/public/observations`, which is available on self-hosted and
    cloud Langfuse. Paginates until `limit` rows are collected.
    """
    import httpx  # local import — only needed for the API source

    host = host.rstrip("/")
    out: List[dict] = []
    page = 1
    with httpx.Client(auth=(public_key, secret_key), timeout=30.0) as client:
        while len(out) < limit:
            params: Dict[str, Any] = {
                "type": "GENERATION",
                "page": page,
                "limit": min(page_size, limit - len(out)),
            }
            if from_time:
                params["fromStartTime"] = from_time
            if to_time:
                params["toStartTime"] = to_time
            if name:
                params["name"] = name

            resp = client.get(f"{host}/api/public/observations", params=params)
            resp.raise_for_status()
            body = resp.json()
            rows = body.get("data", []) if isinstance(body, dict) else (body or [])
            if not rows:
                break
            out.extend(rows)

            meta = body.get("meta", {}) if isinstance(body, dict) else {}
            total_pages = meta.get("totalPages")
            if total_pages is not None and page >= total_pages:
                break
            page += 1

    return out[:limit]


# ── Push into Forkmark ────────────────────────────────────────────────────────

def import_to_forkmark(client, pairs: List[Pair], *, workflow: str, name: str,
                       model_a: str, model_b: str,
                       branch_a_label: Optional[str] = None,
                       branch_b_label: Optional[str] = None,
                       description: str = "") -> Tuple[str, int]:
    """Create one eval run and one comparison per pair via the Forkmark SDK.

    Reuses the same logging path the SDK and no-code runner use, so divergence
    scoring and comparison creation happen automatically server-side.

    Returns (eval_run_id, comparisons_created).
    """
    from ..workflow import WorkflowContext  # local import to avoid import cycle

    branch_a_label = branch_a_label or model_a
    branch_b_label = branch_b_label or model_b

    er = client.create_eval_run(
        workflow_name=workflow,
        name=name,
        description=description or "Imported from Langfuse",
        branch_a_config={"label": branch_a_label, "model_id": model_a},
        branch_b_config={"label": branch_b_label, "model_id": model_b},
        total_cases=len(pairs),
    )
    er_id = er["id"]

    created = 0
    for i, p in enumerate(pairs):
        label = p.label or f"case-{i + 1}"
        wf = WorkflowContext(client, workflow=workflow, input_data=p.input_data,
                             eval_run_id=er_id, test_case_label=label)
        try:
            with wf:
                wf.log_step_output("generation", messages=p.messages,
                                   output=p.output_a, model=model_a, branch="A")
                wf.log_step_output("generation", messages=p.messages,
                                   output=p.output_b, model=model_b, branch="B")
            created += 1
        except Exception as e:  # one bad row shouldn't abort the whole import
            print(f"[forkmark] skipped case {i + 1} ({label}): {e}")

    client.complete_eval_run(er_id, total_cases=created)
    return er_id, created


# ── Orchestration (used by the CLI) ───────────────────────────────────────────

@dataclass
class ImportResult:
    observations: int
    pairs: int
    model_a: Optional[str]
    model_b: Optional[str]
    eval_run_id: Optional[str] = None
    created: int = 0


def run_import(*, file: Optional[str] = None,
               api: Optional[dict] = None,
               model_a: Optional[str] = None, model_b: Optional[str] = None,
               forkmark_url: str = "http://localhost:7700",
               api_key: Optional[str] = None,
               workflow: str = "langfuse-import",
               name: Optional[str] = None,
               branch_a_label: Optional[str] = None,
               branch_b_label: Optional[str] = None,
               dry_run: bool = False) -> ImportResult:
    """End-to-end import. Either `file` or `api` (a dict of fetch kwargs) is required."""
    if file:
        observations = load_from_file(file)
    elif api:
        observations = fetch_from_api(**api)
    else:
        raise ValueError("Provide either file= or api=")

    pairs, model_a, model_b = pair_by_input(observations, model_a, model_b)
    result = ImportResult(observations=len(observations), pairs=len(pairs),
                          model_a=model_a, model_b=model_b)

    if dry_run or not pairs:
        return result

    from ..client import ForkmarkClient
    if not api_key:
        raise ValueError("An API key is required to push (set --api-key or FORKMARK_API_KEY)")
    client = ForkmarkClient(api_key=api_key, base_url=forkmark_url)
    run_name = name or f"Langfuse import: {model_a} vs {model_b}"
    try:
        er_id, created = import_to_forkmark(
            client, pairs, workflow=workflow, name=run_name,
            model_a=model_a, model_b=model_b,
            branch_a_label=branch_a_label, branch_b_label=branch_b_label,
        )
    finally:
        client.close()
    result.eval_run_id = er_id
    result.created = created
    return result
