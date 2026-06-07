"""Output comparator — tiered divergence scoring.

Scorer selection (FM_DIVERGENCE_SCORER env var, default: "auto"):

  auto      — tries 'semantic' first; falls back to 'lexical' if
               sentence-transformers is not installed.
  lexical   — TF-IDF cosine + SequenceMatcher. Zero deps, ~1 ms per pair.
               Dramatically better than raw Jaccard: IDF weighting suppresses
               stopwords; cosine handles length asymmetry. Good for quick
               filtering but still semantically blind.
  semantic  — sentence-transformers all-MiniLM-L6-v2 cosine similarity.
               ~80 MB one-time download, ~50 ms CPU inference per pair.
               Current production standard (Pinecone, Weaviate default encoder).
               Handles paraphrase, synonym substitution, and rephrasing correctly.
               Install:  pip install sentence-transformers
  openai    — OpenAI text-embedding-3-small cosine similarity via API.
               Best commercial embedding with full semantic coverage.
               Requires FM_OPENAI_API_KEY (or OPENAI_API_KEY).
               Override model with FM_EMBED_MODEL.
  llm_judge — G-Eval style LLM-as-judge via any OpenAI-compatible endpoint.
               Gold standard: highest correlation with human judgments
               (MT-Bench 2023). 2–5 s per pair, ~$0.01 per comparison.
               Use for final eval reviews, not real-time SDK calls.
               Requires FM_OPENAI_API_KEY + FM_JUDGE_MODEL (default: gpt-4o-mini)
               Override base URL with FM_JUDGE_BASE_URL (supports Ollama, etc.).

Industry context:
  The LLMOps field has converged on two tiers:
    1. Embedding cosine (semantic) for fast batch scoring — used by Braintrust,
       Humanloop, LangSmith as their default non-LLM metric.
    2. LLM-as-judge for final review and ambiguous cases — pioneered by MT-Bench
       (Zheng et al. 2023), now the de-facto gold standard for nuanced quality.
  Pure lexical metrics (BLEU, ROUGE, Jaccard) are considered outdated for
  output comparison. They fail on paraphrase and reward superficial overlap.
"""
from __future__ import annotations

import math
import os
import re
import threading
from difflib import SequenceMatcher
from typing import Dict, List, Optional

# Shared httpx client for OpenAI API calls — reuses TCP connections
_httpx_client = None
_httpx_lock = threading.Lock()

def _get_httpx_client():
    global _httpx_client
    if _httpx_client is None:
        with _httpx_lock:
            if _httpx_client is None:
                import httpx
                _httpx_client = httpx.Client(timeout=30.0)
    return _httpx_client


# ── Scorer configuration ──────────────────────────────────────────────────────

_SCORER    = os.getenv("FM_DIVERGENCE_SCORER", "auto").lower()
_ST_MODEL  = os.getenv("FM_ST_MODEL", "all-MiniLM-L6-v2")


# ── 1. Lexical scorer — TF-IDF cosine + SequenceMatcher ──────────────────────

def _tokenize(text: str) -> List[str]:
    return re.findall(r'\w+', text.lower())


def _tfidf_cosine(a: str, b: str) -> float:
    """TF-IDF weighted cosine similarity between two text strings.

    Better than Jaccard because:
      - IDF down-weights common function words (the, a, is, was …)
      - Cosine normalises for document length differences
      - Captures term importance, not just binary presence/absence
    """
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0

    vocab = set(ta) | set(tb)

    # IDF: log(2 / df) where df is 1 or 2 (number of docs containing the term)
    idf: Dict[str, float] = {}
    for w in vocab:
        df = int(w in set(ta)) + int(w in set(tb))
        idf[w] = math.log(2.0 / df) if df else 0.0

    # Normalised TF vectors over the shared vocabulary
    def _tf_vec(tokens: List[str]) -> Dict[str, float]:
        n = len(tokens)
        freq: Dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        return {w: freq.get(w, 0) / n for w in vocab}

    va = _tf_vec(ta)
    vb = _tf_vec(tb)

    dot    = sum(va[w] * vb[w] * idf[w] ** 2 for w in vocab)
    norm_a = math.sqrt(sum((va[w] * idf[w]) ** 2 for w in vocab))
    norm_b = math.sqrt(sum((vb[w] * idf[w]) ** 2 for w in vocab))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return min(dot / (norm_a * norm_b), 1.0)


def _lexical_divergence(a: str, b: str) -> float:
    """TF-IDF cosine (70 %) + SequenceMatcher (30 %) divergence."""
    tfidf_sim = _tfidf_cosine(a, b)
    seq_sim   = SequenceMatcher(None, a, b).ratio()
    similarity = tfidf_sim * 0.7 + seq_sim * 0.3
    return round(1.0 - min(max(similarity, 0.0), 1.0), 4)


# ── 2. Semantic scorer — sentence-transformers ────────────────────────────────

_ST_UNAVAILABLE = object()  # distinct sentinel: import failed, don't retry
_st_model = None
_st_lock  = threading.Lock()


def _get_st_model():
    """Lazy-load sentence-transformers model once, thread-safe."""
    global _st_model
    if _st_model is not None:
        return _st_model
    with _st_lock:
        if _st_model is not None:
            return _st_model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            _st_model = SentenceTransformer(_ST_MODEL)
        except ImportError:
            _st_model = _ST_UNAVAILABLE
    return _st_model


def _semantic_divergence(a: str, b: str) -> Optional[float]:
    """Cosine divergence via sentence-transformers. None if unavailable."""
    model = _get_st_model()
    if model is _ST_UNAVAILABLE:
        return None
    try:
        import numpy as np  # type: ignore
        embs = model.encode([a or " ", b or " "])
        ea, eb = embs[0], embs[1]
        na = float(np.linalg.norm(ea))
        nb = float(np.linalg.norm(eb))
        if na == 0 or nb == 0:
            return 0.0
        cosine = float(np.dot(ea, eb) / (na * nb))
        # cosine ∈ [-1, 1]; map to divergence ∈ [0, 1]
        return round((1.0 - cosine) / 2.0, 4)
    except Exception:
        return None


# ── 3. OpenAI embedding scorer ────────────────────────────────────────────────

def _openai_divergence(a: str, b: str) -> Optional[float]:
    """Cosine divergence via OpenAI embeddings API. None if key missing."""
    api_key = os.getenv("FM_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("FM_EMBED_MODEL", "text-embedding-3-small")
    try:
        client = _get_httpx_client()
        resp = client.post(
            "https://api.openai.com/v1/embeddings",
            json={"input": [a or " ", b or " "], "model": model},
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        ea   = data[0]["embedding"]
        eb   = data[1]["embedding"]

        dot  = sum(x * y for x, y in zip(ea, eb))
        na   = math.sqrt(sum(x * x for x in ea))
        nb   = math.sqrt(sum(y * y for y in eb))
        if na == 0 or nb == 0:
            return 0.0
        cosine = dot / (na * nb)
        return round((1.0 - cosine) / 2.0, 4)
    except Exception:
        return None


# ── 4. LLM-as-judge scorer (G-Eval style) ────────────────────────────────────

_JUDGE_PROMPT = """\
You are an expert evaluator comparing two AI-generated outputs for the same input.

Rate how divergent these two outputs are on a scale from 0.0 to 1.0:
  0.0 = identical or semantically equivalent (same facts, same conclusion)
  0.2 = minor differences in phrasing or style; meaning is the same
  0.5 = moderate divergence — different emphasis, structure, or level of detail
  0.8 = major divergence — different conclusions, facts, or recommendations
  1.0 = completely different outputs with no meaningful overlap

Output A:
{output_a}

Output B:
{output_b}

Respond with ONLY a single decimal number between 0.0 and 1.0.
No explanation. No other text."""


def _llm_judge_divergence(a: str, b: str) -> Optional[float]:
    """G-Eval style LLM-as-judge divergence. None if API key missing."""
    api_key  = os.getenv("FM_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("FM_JUDGE_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model    = os.getenv("FM_JUDGE_MODEL", "gpt-4o-mini")

    if not api_key:
        return None

    # Truncate long outputs to control cost (~$0.001 per comparison at gpt-4o-mini rates)
    a_trunc = a[:2000] + ("…" if len(a) > 2000 else "")
    b_trunc = b[:2000] + ("…" if len(b) > 2000 else "")
    prompt  = _JUDGE_PROMPT.format(output_a=a_trunc, output_b=b_trunc)

    try:
        client = _get_httpx_client()
        resp = client.post(
            f"{base_url}/chat/completions",
            json={
                "model":       model,
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0.0,   # deterministic scoring
                "max_tokens":  10,
            },
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            timeout=30.0,
        )
        resp.raise_for_status()
        raw   = resp.json()["choices"][0]["message"]["content"].strip()
        score = float(raw.split()[0].rstrip(",.:;"))
        return round(min(max(score, 0.0), 1.0), 4)
    except Exception:
        return None


# ── Public interface ──────────────────────────────────────────────────────────

def divergence_score(a: str, b: str) -> float:
    """Compute divergence ∈ [0, 1] using the configured scorer.

    Cascade on failure:
      auto      → semantic → lexical
      semantic  → semantic → lexical
      openai    → openai   → lexical
      llm_judge → judge    → lexical
      lexical   → lexical  (always succeeds)
    """
    s = _SCORER

    if s in ("auto", "semantic"):
        result = _semantic_divergence(a, b)
        if result is not None:
            return result
        return _lexical_divergence(a, b)

    if s == "openai":
        result = _openai_divergence(a, b)
        return result if result is not None else _lexical_divergence(a, b)

    if s == "llm_judge":
        result = _llm_judge_divergence(a, b)
        return result if result is not None else _lexical_divergence(a, b)

    # explicit "lexical" or unknown value
    return _lexical_divergence(a, b)


def scorer_name() -> str:
    """Return the active scorer name for API metadata / UI display."""
    s = _SCORER
    if s in ("auto", "semantic"):
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            return f"semantic:{_ST_MODEL}"
        except ImportError:
            return "lexical:tfidf"
    if s == "openai":
        return f"openai:{os.getenv('FM_EMBED_MODEL', 'text-embedding-3-small')}"
    if s == "llm_judge":
        return f"llm_judge:{os.getenv('FM_JUDGE_MODEL', 'gpt-4o-mini')}"
    return "lexical:tfidf"


def inline_diff(a: str, b: str) -> List[dict]:
    """Word-level diff between two outputs for UI rendering."""
    words_a = (a or "").split()
    words_b = (b or "").split()
    sm      = SequenceMatcher(None, words_a, words_b)
    result  = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            result.append({"type": "equal",   "text": " ".join(words_a[i1:i2])})
        elif tag == "replace":
            result.append({"type": "removed", "text": " ".join(words_a[i1:i2])})
            result.append({"type": "added",   "text": " ".join(words_b[j1:j2])})
        elif tag == "delete":
            result.append({"type": "removed", "text": " ".join(words_a[i1:i2])})
        elif tag == "insert":
            result.append({"type": "added",   "text": " ".join(words_b[j1:j2])})
    return result


def summarize_divergence(a: str, b: str, score: float) -> str:
    """Human-readable summary of a divergence score."""
    if score < 0.05:
        return "Outputs are nearly identical."
    if score < 0.2:
        return "Minor wording differences; same substance."
    if score < 0.5:
        return "Moderate divergence — different emphasis or structure."
    return "High divergence — materially different outputs. Review carefully."
