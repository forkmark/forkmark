# Show HN: Forkmark — Open-source A/B comparison platform for LLM workflows with DPO export

Hi HN,

I built Forkmark because I got tired of the "vibes-based evaluation" loop — change a prompt, eyeball a few outputs, ship it, and hope for the best.

Forkmark is a self-hosted platform that makes structured pairwise evaluation the core primitive of your LLM quality process. You define two branch configurations (different models, prompts, or parameters), run them against the same test inputs, and get side-by-side comparisons with automatic divergence scoring.

The key insight: if you're already doing A/B evaluation with structured preference data (which branch won, confidence level, rationale), you're generating exactly what DPO and RLHF fine-tuning need. Forkmark makes this explicit — every decision you record contributes to a preference corpus you can export with one click.

What it does:

- Pairwise A/B comparison with position debiasing (randomized presentation order)
- Four-tier divergence scoring: lexical → semantic → embedding → LLM-as-judge
- Structured decisions with choice, confidence, and rationale
- One-click export to DPO, OpenAI fine-tuning, CSV, and JSONL formats
- Consent-gated data collection — reviewers opt in to having decisions used for training
- No-code workflow runner for non-technical team members
- SQLite (dev) / PostgreSQL (prod)

What it doesn't do: Forkmark is not a logging/observability tool. It doesn't replace LangSmith or Weights & Biases for production monitoring. It's specifically for structured evaluation and preference data collection.

Stack: Python (FastAPI) + React SPA, single-process deployment, runs on a laptop with `python start.py`.

GitHub: https://github.com/forkmark/forkmark
Docs: https://docs.forkmark.dev

Would love feedback, especially from teams doing human evaluation at scale or anyone who's tried to build DPO training datasets manually.
