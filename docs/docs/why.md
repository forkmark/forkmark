# Why Forkmark

Most LLM evaluation tools start from logging and tack on evaluation as an afterthought. Forkmark inverts this: **structured pairwise comparison is the core primitive**, and everything else — scoring, export, training data — flows from it.

## The problem with current approaches

LLM teams iterate fast. You change a prompt, swap a model, tweak retrieval parameters, and redeploy. But how do you know if the change actually made things better?

Common approaches have real limitations:

**Vibes-based evaluation** — You eyeball a few outputs, decide it "feels better," and ship. This doesn't scale, isn't reproducible, and can't catch regressions across edge cases.

**Automated metrics** — BLEU, ROUGE, and other reference-based metrics are fast but poorly correlated with human preference for open-ended generation. You optimize for a number that doesn't reflect what users actually care about.

**LLM-as-judge** — Sending outputs to GPT-4 for scoring is convenient but introduces its own biases (position bias, verbosity bias, self-preference). Without human ground truth, you're building on sand.

**Logging platforms with eval bolted on** — Tools like LangSmith, Braintrust, and Weights & Biases start from observability and add evaluation as a feature. The evaluation UX is secondary to the logging story, and the data model wasn't designed for structured preference collection.

## How Forkmark is different

### Comparison-first data model

Every evaluation in Forkmark is a pairwise comparison. You define two branch configurations (different models, prompts, or parameters), run them against the same inputs, and get structured side-by-side outputs.

This isn't just a UI choice — it's a data model decision. Every `Comparison` entity pairs two `StepOutput` records and captures automatic divergence scores. Every `Decision` records a structured human verdict with choice, confidence, rationale for selection, and rationale for rejection.

### Position debiasing built in

LLM judges and human reviewers both exhibit position bias — they tend to prefer whichever output appears first. Forkmark randomizes presentation order at the comparison level, ensuring your evaluation data isn't systematically skewed.

### Four-tier divergence scoring

Not every comparison needs human review. Forkmark's automatic scoring pipeline identifies which outputs actually differ:

- **Lexical** — edit distance for surface-level changes
- **Semantic** — sentence-transformer similarity for paraphrase detection
- **Embedding** — OpenAI embedding cosine distance for deeper semantic comparison
- **LLM-as-judge** — model-graded quality assessment with configurable rubrics

Reviewers focus their time on comparisons that actually diverge, rather than confirming that two identical outputs are identical.

### DPO export as a first-class output

Here's the key insight: if you're already doing structured A/B evaluation with preference data, you're generating exactly what DPO and RLHF fine-tuning need — labeled pairs of (chosen, rejected) outputs with associated prompts.

Forkmark makes this explicit. Every decision you record contributes to a preference corpus. When you're ready to fine-tune, export your data in DPO, OpenAI fine-tuning, or raw JSONL format with one click.

This creates a flywheel: evaluation improves your model, which changes your outputs, which requires more evaluation, which generates more training data.

### Consent-gated data collection

Using human evaluation data for model training raises ethical questions. Forkmark's consent framework lets reviewers explicitly opt in or out of having their decisions included in training exports. Consent is tracked per-reviewer, per-workflow, and can be revoked at any time.

### Self-hosted by design

Your prompts, outputs, and evaluation data are sensitive. Forkmark runs entirely on your infrastructure — there are no external API calls except to the LLM providers you explicitly configure.

The default setup is a single Python process with SQLite, deployable on a laptop in 30 seconds. Scale to PostgreSQL and multiple workers when you need it.

## Who is Forkmark for?

**AI engineers** who want rigorous A/B testing of prompt and model changes before shipping to production.

**ML teams** building internal evaluation pipelines who need structured preference data for fine-tuning.

**Quality teams** running human evaluation at scale who need review assignment, progress tracking, and inter-annotator agreement metrics.

**Research groups** conducting pairwise preference studies who need consent management and structured export.

## What Forkmark is not

Forkmark is not a logging or observability platform. It doesn't instrument your production traffic or provide real-time dashboards of latency and token usage. Use your existing observability stack for that.

Forkmark is not an auto-eval framework. It doesn't replace the need for human judgment — it structures and amplifies it.

Forkmark is not a model hosting platform. It calls your existing LLM endpoints and evaluates the outputs.

## Getting started

```bash
git clone https://github.com/forkmark/forkmark.git
cd forkmark
python run.py
```

Open `http://localhost:7700`, try the Demo Gallery, and run your first evaluation in under five minutes. See the [quickstart guide](getting-started/quickstart.md) for a full walkthrough.
