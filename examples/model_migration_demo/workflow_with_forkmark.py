"""
ProductContentPipeline — With Forkmark Model Comparison
=========================================================

This is workflow_original.py with Forkmark integration added.

The goal: before committing to a model upgrade from gpt-3.5-turbo to
gpt-4o-mini, run both models over your real production inputs and review
every case where outputs meaningfully differ.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT CHANGED FROM workflow_original.py (4 additions):

  1. Import ForkmarkClient              (+2 lines)
  2. Initialise client in __init__       (+3 lines)
  3. Run each product through BOTH models,
     log steps to Forkmark, create comparison
                                         (+~40 lines in process_with_comparison())
  4. CLI flag --forkmark-url            (+2 lines)

The core pipeline steps (classify_product, generate_title,
generate_description, generate_seo_meta) are IDENTICAL to
workflow_original.py — untouched.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
    export OPENAI_API_KEY=sk-...
    export FORKMARK_API_KEY=fm_...
    python workflow_with_forkmark.py
    python workflow_with_forkmark.py --sku SUP-7743
    python workflow_with_forkmark.py --baseline gpt-3.5-turbo --challenger gpt-4o-mini
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import argparse
from dataclasses import dataclass, field
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ── NEW: Forkmark SDK import ─────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
from forkmark.client import ForkmarkClient
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("product_pipeline.forkmark")


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class PipelineConfig:
    baseline_model:   str   = "gpt-3.5-turbo"       # model currently in production
    challenger_model: str   = "gpt-4o-mini"          # model under evaluation
    temperature:      float = 0.3
    max_tokens:       int   = 800
    timeout_s:        float = 30.0
    openai_api_key:   str   = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_base_url:  str   = "https://api.openai.com/v1"

    # ── NEW: Forkmark settings ────────────────────────────────────────────────
    forkmark_api_key: str  = field(default_factory=lambda: os.environ.get("FORKMARK_API_KEY", ""))
    forkmark_url:     str  = "http://127.0.0.1:7700"
    workflow_name:     str  = "product-content-pipeline"
    eval_run_name:     str  = "gpt-3.5-turbo vs gpt-4o-mini — Product Content"
    # ─────────────────────────────────────────────────────────────────────────

    def validate(self):
        if not self.openai_api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set.\n  export OPENAI_API_KEY=sk-..."
            )
        if not self.forkmark_api_key:
            raise EnvironmentError(
                "FORKMARK_API_KEY is not set.\n"
                "  Bootstrap one with: curl -X POST http://localhost:7700/api/keys "
                "-H 'X-API-Key: <bootstrap-token>' -d '{\"name\":\"demo-key\"}'"
            )


# ── Data models (unchanged from workflow_original.py) ─────────────────────────

@dataclass
class SupplierProduct:
    sku:               str
    raw_title:         str
    specs:             str
    supplier_category: str
    cost_price:        float
    brand:             Optional[str] = None
    images_available:  int = 0
    notes:             str = ""


@dataclass
class ProductClassification:
    canonical_category: str
    product_type:       str
    key_features:       list[str]
    target_audience:    str
    usp:                str
    model_used:         str = ""
    latency_ms:         int = 0


@dataclass
class ProductTitle:
    title:        str
    alternatives: list[str]
    char_count:   int = 0
    model_used:   str = ""
    latency_ms:   int = 0


@dataclass
class ProductDescription:
    headline:   str
    body:       str
    bullets:    list[str]
    model_used: str = ""
    latency_ms: int = 0


@dataclass
class SEOMeta:
    meta_title:       str
    meta_description: str
    keywords:         list[str]
    model_used:       str = ""
    latency_ms:       int = 0


@dataclass
class PipelineResult:
    product:          SupplierProduct
    classification:   Optional[ProductClassification] = None
    title:            Optional[ProductTitle]           = None
    description:      Optional[ProductDescription]    = None
    seo_meta:         Optional[SEOMeta]                = None
    error:            Optional[str]                    = None
    total_latency_ms: int                              = 0
    comparison_id:    Optional[str]                    = None    # NEW: Forkmark comparison ID

    @property
    def success(self) -> bool:
        return self.error is None and all([
            self.classification, self.title, self.description, self.seo_meta
        ])


# ── OpenAI client (unchanged) ──────────────────────────────────────────────────

class OpenAIClient:
    def __init__(self, api_key: str, base_url: str, timeout_s: float):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout_s,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def chat(self, messages: list[dict], model: str, temperature: float, max_tokens: int) -> tuple[str, int, int]:
        payload = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "messages": messages}
        resp    = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data    = resp.json()
        usage   = data.get("usage", {})
        return (
            data["choices"][0]["message"]["content"],
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    def close(self):
        self._client.close()


# ── Pipeline ───────────────────────────────────────────────────────────────────

class ProductContentPipelineWithForkmark:
    """
    Identical pipeline logic to workflow_original.py, extended to:

      1. Run each product through BOTH the baseline and challenger model.
      2. Log every step's input/output to Forkmark for both branches.
      3. Create a Forkmark comparison so the team can review divergence
         before deciding to promote the challenger model to production.

    The pipeline step methods (classify_product, generate_title, etc.) are
    identical to workflow_original.py — they are called twice per product,
    once per model.
    """

    SYSTEM_PROMPT = (
        "You are a senior e-commerce content specialist at StyleForge Commerce. "
        "You write clear, accurate, customer-focused product content. "
        "Always respond with valid JSON matching the schema provided. "
        "Do not include markdown code fences in your response."
    )

    WORKFLOW_NAME = "product-content-pipeline"

    def __init__(self, config: PipelineConfig):
        self.config  = config
        self.llm     = OpenAIClient(config.openai_api_key, config.openai_base_url, config.timeout_s)

        # ── NEW: initialise Forkmark client and create eval run ──────────────
        self.fp = ForkmarkClient(
            api_key      = config.forkmark_api_key,
            base_url     = config.forkmark_url,
            default_workflow = self.WORKFLOW_NAME,
        )
        self._eval_run_id = self._init_eval_run()
        # ─────────────────────────────────────────────────────────────────────

    # ── NEW: Forkmark eval run setup ─────────────────────────────────────────

    def _init_eval_run(self) -> str:
        """Create a Forkmark eval run to group all product comparisons."""
        er = self.fp.create_eval_run(
            workflow_name  = self.WORKFLOW_NAME,
            name           = self.config.eval_run_name,
            description    = (
                f"Evaluating whether upgrading from {self.config.baseline_model} to "
                f"{self.config.challenger_model} improves product content quality "
                f"across title, description, and SEO meta generation."
            ),
            branch_a_config = {
                "label":       f"{self.config.baseline_model} (Production / Baseline)",
                "model_id":    self.config.baseline_model,
                "temperature": self.config.temperature,
            },
            branch_b_config = {
                "label":       f"{self.config.challenger_model} (Challenger)",
                "model_id":    self.config.challenger_model,
                "temperature": self.config.temperature,
            },
            total_cases = 0,   # updated on completion
        )
        log.info(f"Forkmark eval run created: {er['id']}")
        return er["id"]

    # ── Pipeline step methods (identical to workflow_original.py) ─────────────

    def _build_classify_prompt(self, product: SupplierProduct) -> str:
        return f"""
Classify this product from our supplier feed and extract structured metadata.

Supplier data:
  SKU:               {product.sku}
  Raw title:         {product.raw_title}
  Specs:             {product.specs}
  Supplier category: {product.supplier_category}
  Brand:             {product.brand or "unbranded"}

Return JSON with exactly these fields:
{{
  "canonical_category": "Top Level > Sub-category > Type",
  "product_type":       "specific product type in 2-4 words",
  "key_features":       ["feature 1", "feature 2", "feature 3", "feature 4", "feature 5"],
  "target_audience":    "primary customer segment in one phrase",
  "usp":                "single most compelling selling point in one sentence"
}}
""".strip()

    def _build_title_prompt(self, product: SupplierProduct, cls: ProductClassification) -> str:
        return f"""
Write an SEO-optimised product title for this item.
  Raw supplier title: {product.raw_title}
  Product type:       {cls.product_type}
  Key features:       {", ".join(cls.key_features[:3])}
  USP:                {cls.usp}

Return JSON: {{"title": "primary title (max 80 chars)", "alternatives": ["alt 1", "alt 2"]}}
""".strip()

    def _build_description_prompt(self, product: SupplierProduct, cls: ProductClassification, title: ProductTitle) -> str:
        return f"""
Write the customer-facing product description.
  Title:        {title.title}
  Type:         {cls.product_type}
  Key features: {", ".join(cls.key_features)}
  Audience:     {cls.target_audience}
  Raw specs:    {product.specs}

Return JSON:
{{
  "headline": "hook line (max 120 chars)",
  "body":     "2-3 paragraph description",
  "bullets":  ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5"]
}}
""".strip()

    def _build_seo_prompt(self, cls: ProductClassification, title: ProductTitle, desc: ProductDescription) -> str:
        return f"""
Write the SEO meta fields for this product page.
  Title:        {title.title}
  Headline:     {desc.headline}
  Key features: {", ".join(cls.key_features)}

Return JSON:
{{
  "meta_title":       "meta title (max 60 chars)",
  "meta_description": "meta description (max 160 chars)",
  "keywords":         ["keyword1", ..., "keyword10"]
}}
""".strip()

    def _call_step(self, prompt: str, model: str) -> tuple[str, int, int, int]:
        """Call LLM for one step. Returns (content, tok_in, tok_out, latency_ms)."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]
        t0 = time.perf_counter()
        content, tok_in, tok_out = self.llm.chat(
            messages,
            model       = model,
            temperature = self.config.temperature,
            max_tokens  = self.config.max_tokens,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return content, tok_in, tok_out, latency_ms

    def _run_model(self, product: SupplierProduct, model: str) -> tuple[list[dict], list[str], list[str], list[int], list[int]]:
        """
        Run all four pipeline steps for one product with one model.

        Returns:
            outputs      — list of 4 raw JSON strings (one per step)
            step_names   — list of step name strings
            prompts      — list of prompt strings (for Forkmark input_messages)
            toks_in      — input token counts per step
            latencies    — latency_ms per step
        """
        step_names  = ["classify_product", "generate_title", "generate_description", "generate_seo_meta"]
        prompts_out = []
        outputs     = []
        toks_in     = []
        latencies   = []

        # Step 1 — classify
        p1 = self._build_classify_prompt(product)
        o1, ti1, _, l1 = self._call_step(p1, model)
        cls_data = json.loads(o1)
        cls = ProductClassification(**{k: cls_data[k] for k in ["canonical_category","product_type","key_features","target_audience","usp"]})
        prompts_out.append(p1); outputs.append(o1); toks_in.append(ti1); latencies.append(l1)

        # Step 2 — title
        p2 = self._build_title_prompt(product, cls)
        o2, ti2, _, l2 = self._call_step(p2, model)
        ttl_data = json.loads(o2)
        ttl = ProductTitle(title=ttl_data["title"], alternatives=ttl_data.get("alternatives", []))
        prompts_out.append(p2); outputs.append(o2); toks_in.append(ti2); latencies.append(l2)

        # Step 3 — description
        p3 = self._build_description_prompt(product, cls, ttl)
        o3, ti3, _, l3 = self._call_step(p3, model)
        prompts_out.append(p3); outputs.append(o3); toks_in.append(ti3); latencies.append(l3)
        desc_data = json.loads(o3)
        desc = ProductDescription(headline=desc_data["headline"], body=desc_data["body"], bullets=desc_data["bullets"])

        # Step 4 — SEO meta
        p4 = self._build_seo_prompt(cls, ttl, desc)
        o4, ti4, _, l4 = self._call_step(p4, model)
        prompts_out.append(p4); outputs.append(o4); toks_in.append(ti4); latencies.append(l4)

        return outputs, step_names, prompts_out, toks_in, latencies

    # ── NEW: process_with_comparison — main entry point with Forkmark ─────────

    def process_with_comparison(self, product: SupplierProduct) -> PipelineResult:
        """
        Run BOTH models for one product, log every step to Forkmark,
        and create a comparison. Returns the baseline model's result.

        This is the only materially new method. Everything else above is
        unchanged plumbing.
        """
        result  = PipelineResult(product=product)
        t_start = time.perf_counter()

        log.info(f"Processing {product.sku}: {product.raw_title!r}")

        try:
            # ── 1. Create a Forkmark workflow run for this product ───────────
            run = self.fp.start_run(
                workflow       = self.WORKFLOW_NAME,
                input_data     = {"sku": product.sku, "raw_title": product.raw_title, "specs": product.specs},
                eval_run_id    = self._eval_run_id,
                test_case_label = product.sku,
            )
            run_id = run["id"]

            # ── 2. Create Branch A (baseline) and Branch B (challenger) ───────
            branch_a = self.fp.create_branch(
                run_id        = run_id,
                name          = f"{self.config.baseline_model}@t{self.config.temperature}",
                model_id      = self.config.baseline_model,
                temperature   = self.config.temperature,
                system_prompt = self.SYSTEM_PROMPT,
                is_baseline   = True,
            )
            branch_b = self.fp.create_branch(
                run_id        = run_id,
                name          = f"{self.config.challenger_model}@t{self.config.temperature}",
                model_id      = self.config.challenger_model,
                temperature   = self.config.temperature,
                system_prompt = self.SYSTEM_PROMPT,
                is_baseline   = False,
            )

            # ── 3. Run baseline model ─────────────────────────────────────────
            log.debug(f"  Running baseline ({self.config.baseline_model})...")
            outputs_a, step_names, prompts, toks_a, lats_a = self._run_model(
                product, self.config.baseline_model
            )

            # ── 4. Run challenger model ───────────────────────────────────────
            log.debug(f"  Running challenger ({self.config.challenger_model})...")
            outputs_b, _, _, toks_b, lats_b = self._run_model(
                product, self.config.challenger_model
            )

            # ── 5. Log all steps to Forkmark for both branches ───────────────
            for i, step_name in enumerate(step_names):
                input_messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": prompts[i]},
                ]
                self.fp.log_step(
                    run_id         = run_id,
                    branch_id      = branch_a["id"],
                    step_name      = step_name,
                    step_index     = i,
                    input_messages = input_messages,
                    output_text    = outputs_a[i],
                    model_id       = self.config.baseline_model,
                    temperature    = self.config.temperature,
                    tokens_input   = toks_a[i],
                    latency_ms     = lats_a[i],
                )
                self.fp.log_step(
                    run_id         = run_id,
                    branch_id      = branch_b["id"],
                    step_name      = step_name,
                    step_index     = i,
                    input_messages = input_messages,
                    output_text    = outputs_b[i],
                    model_id       = self.config.challenger_model,
                    temperature    = self.config.temperature,
                    tokens_input   = toks_b[i],
                    latency_ms     = lats_b[i],
                )

            # ── 6. Complete the run and create the comparison ─────────────────
            self.fp.complete_run(run_id)
            comp = self.fp.create_comparison(
                run_id      = run_id,
                branch_a_id = branch_a["id"],
                branch_b_id = branch_b["id"],
                step_names  = step_names,
            )
            result.comparison_id = comp["id"]

            # ── 7. Parse baseline output into structured result ───────────────
            cls_data  = json.loads(outputs_a[0])
            ttl_data  = json.loads(outputs_a[1])
            desc_data = json.loads(outputs_a[2])
            seo_data  = json.loads(outputs_a[3])

            result.classification = ProductClassification(
                **{k: cls_data[k] for k in ["canonical_category","product_type","key_features","target_audience","usp"]},
                model_used = self.config.baseline_model,
            )
            result.title = ProductTitle(
                title        = ttl_data["title"],
                alternatives = ttl_data.get("alternatives", []),
                char_count   = len(ttl_data["title"]),
                model_used   = self.config.baseline_model,
            )
            result.description = ProductDescription(
                headline   = desc_data["headline"],
                body       = desc_data["body"],
                bullets    = desc_data["bullets"],
                model_used = self.config.baseline_model,
            )
            result.seo_meta = SEOMeta(
                meta_title       = seo_data["meta_title"],
                meta_description = seo_data["meta_description"],
                keywords         = seo_data["keywords"],
                model_used       = self.config.baseline_model,
            )

        except json.JSONDecodeError as e:
            result.error = f"JSON parse error: {e}"
            log.error(f"  {product.sku} — JSON parse error: {e}")
        except Exception as e:
            result.error = str(e)
            log.error(f"  {product.sku} — Error: {e}")

        result.total_latency_ms = int((time.perf_counter() - t_start) * 1000)
        status = "✓" if result.success else f"✗ {result.error}"
        fm_ref = f"  comparison: {result.comparison_id}" if result.comparison_id else ""
        log.info(f"  {product.sku} — {status}  ({result.total_latency_ms}ms){fm_ref}")
        return result

    def finish_eval_run(self, total_cases: int):
        """Call after all products are processed to mark the eval run complete."""
        self.fp.complete_eval_run(self._eval_run_id, total_cases=total_cases)
        log.info(f"Forkmark eval run completed: {self._eval_run_id}")

    def close(self):
        self.llm.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Sample products (identical to workflow_original.py) ───────────────────────

from workflow_original import SAMPLE_PRODUCTS


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="StyleForge product pipeline with Forkmark model comparison"
    )
    parser.add_argument("--sku",        help="Process only this SKU")
    parser.add_argument("--baseline",   default="gpt-3.5-turbo", help="Baseline (production) model")
    parser.add_argument("--challenger", default="gpt-4o-mini",   help="Challenger (candidate) model")
    parser.add_argument("--forkmark-url", default="http://127.0.0.1:7700")
    args = parser.parse_args()

    config = PipelineConfig(
        baseline_model   = args.baseline,
        challenger_model = args.challenger,
        forkmark_url    = args.forkmark_url,
        eval_run_name    = f"{args.baseline} vs {args.challenger} — Product Content",
    )
    config.validate()

    products = SAMPLE_PRODUCTS
    if args.sku:
        products = [p for p in products if p.sku == args.sku]
        if not products:
            print(f"SKU not found: {args.sku}")
            sys.exit(1)

    print(f"\nStyleForge Product Pipeline + Forkmark Model Comparison")
    print(f"Baseline:   {config.baseline_model}  (production)")
    print(f"Challenger: {config.challenger_model}  (under evaluation)")
    print(f"Products:   {len(products)}")
    print(f"Forkmark:  {config.forkmark_url}")
    print("─" * 65)

    passed = 0
    with ProductContentPipelineWithForkmark(config) as pipeline:
        for product in products:
            result = pipeline.process_with_comparison(product)
            if result.success:
                passed += 1
                div_ref = f"  →  comparison {result.comparison_id[:8]}..." if result.comparison_id else ""
                print(f"  ✓  {product.sku}  {result.title.title!r}{div_ref}")
            else:
                print(f"  ✗  {product.sku}  ERROR: {result.error}")

        pipeline.finish_eval_run(total_cases=passed)

    print("─" * 65)
    print(f"\n  {passed}/{len(products)} products compared successfully")
    print(f"\n  Open Forkmark dashboard to review results:")
    print(f"  {config.forkmark_url.replace('7700','5173')}  →  Eval Runs  →  {config.eval_run_name}")
    print()
    print("  For each product, you'll see:")
    print("  • Side-by-side outputs per step (classify / title / description / SEO)")
    print("  • Divergence score per step — which steps changed most?")
    print("  • Overall divergence — is gpt-4o-mini materially different?")
    print("  • Human review queue — record your preference: A / B / tie")
    print()


if __name__ == "__main__":
    main()
