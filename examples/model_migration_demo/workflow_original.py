"""
ProductContentPipeline — Original Production Workflow
======================================================

This is the existing pipeline at StyleForge Commerce (fictional), a mid-size
e-commerce retailer. It takes raw supplier product data and generates
structured, publish-ready content using GPT-3.5-turbo.

The pipeline runs nightly over the new-product queue, generating:
  1. Canonical product category + feature classification
  2. SEO-optimised product title
  3. Customer-facing product description
  4. SEO meta title, meta description, and keyword set

This file represents the state of the codebase BEFORE any model migration
work or Forkmark integration. It is fully functional as-is.

Usage:
    export OPENAI_API_KEY=sk-...
    python workflow_original.py
    python workflow_original.py --sku SUP-7743          # single product
    python workflow_original.py --dry-run               # validate config only
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import argparse
from dataclasses import dataclass, field, asdict
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("product_pipeline")


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class PipelineConfig:
    model:           str   = "gpt-3.5-turbo"
    temperature:     float = 0.3
    max_tokens:      int   = 800
    timeout_s:       float = 30.0
    openai_api_key:  str   = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_base_url: str   = "https://api.openai.com/v1"

    def validate(self):
        if not self.openai_api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. Export it before running:\n"
                "  export OPENAI_API_KEY=sk-..."
            )


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class SupplierProduct:
    """Raw product data as received from the supplier feed."""
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
    """Step 1 output: structured category and feature extraction."""
    canonical_category:    str           # e.g. "Electronics > Audio > Headphones"
    product_type:          str           # e.g. "Over-ear headphones"
    key_features:          list[str]     # extracted feature bullets
    target_audience:       str           # e.g. "commuters, remote workers"
    usp:                   str           # unique selling proposition in one sentence
    model_used:            str = ""
    latency_ms:            int = 0


@dataclass
class ProductTitle:
    """Step 2 output: SEO-optimised title."""
    title:       str           # the final title (max 80 chars)
    alternatives: list[str]   # 2 alternative title options
    char_count:  int = 0
    model_used:  str = ""
    latency_ms:  int = 0


@dataclass
class ProductDescription:
    """Step 3 output: customer-facing product description."""
    headline:    str   # one-line hook (max 120 chars)
    body:        str   # 2-3 paragraph description
    bullets:     list[str]  # 5 feature bullets for PDP
    model_used:  str = ""
    latency_ms:  int = 0


@dataclass
class SEOMeta:
    """Step 4 output: search engine meta fields."""
    meta_title:       str        # max 60 chars
    meta_description: str        # max 160 chars
    keywords:         list[str]  # 8-10 target keywords
    model_used:       str = ""
    latency_ms:       int = 0


@dataclass
class PipelineResult:
    """Full result for one product through the pipeline."""
    product:         SupplierProduct
    classification:  Optional[ProductClassification] = None
    title:           Optional[ProductTitle]           = None
    description:     Optional[ProductDescription]    = None
    seo_meta:        Optional[SEOMeta]                = None
    error:           Optional[str]                    = None
    total_latency_ms: int                             = 0

    @property
    def success(self) -> bool:
        return self.error is None and all([
            self.classification, self.title, self.description, self.seo_meta
        ])


# ── OpenAI client ──────────────────────────────────────────────────────────────

class OpenAIClient:
    """Thin wrapper around the OpenAI Chat Completions API with retry logic."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._client = httpx.Client(
            base_url=config.openai_base_url,
            headers={
                "Authorization": f"Bearer {config.openai_api_key}",
                "Content-Type":  "application/json",
            },
            timeout=config.timeout_s,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def chat(self, messages: list[dict], **overrides) -> tuple[str, int, int]:
        """
        Call the Chat Completions API.

        Returns:
            (content, tokens_input, tokens_output)
        """
        payload = {
            "model":       overrides.get("model",       self.config.model),
            "temperature": overrides.get("temperature", self.config.temperature),
            "max_tokens":  overrides.get("max_tokens",  self.config.max_tokens),
            "messages":    messages,
        }
        resp = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data  = resp.json()
        usage = data.get("usage", {})
        return (
            data["choices"][0]["message"]["content"],
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    def close(self):
        self._client.close()


# ── Pipeline steps ─────────────────────────────────────────────────────────────

class ProductContentPipeline:
    """
    Four-step pipeline that transforms raw supplier data into publish-ready
    product content using an LLM.

    Step 1 — classify_product:   extract canonical category, type, features, audience
    Step 2 — generate_title:     write an SEO-optimised product title
    Step 3 — generate_description: write headline, body, and feature bullets
    Step 4 — generate_seo_meta:  write meta title, meta description, keywords
    """

    SYSTEM_PROMPT = (
        "You are a senior e-commerce content specialist at StyleForge Commerce. "
        "You write clear, accurate, customer-focused product content. "
        "Always respond with valid JSON matching the schema provided. "
        "Do not include markdown code fences in your response."
    )

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.llm    = OpenAIClient(config)

    # ── Step 1 ─────────────────────────────────────────────────────────────────

    def classify_product(self, product: SupplierProduct) -> ProductClassification:
        prompt = f"""
Classify this product from our supplier feed and extract structured metadata.

Supplier data:
  SKU:               {product.sku}
  Raw title:         {product.raw_title}
  Specs:             {product.specs}
  Supplier category: {product.supplier_category}
  Brand:             {product.brand or "unbranded"}
  Notes:             {product.notes or "none"}

Return JSON with exactly these fields:
{{
  "canonical_category": "Top Level > Sub-category > Type  (e.g. Electronics > Audio > Headphones)",
  "product_type":       "specific product type in 2-4 words",
  "key_features":       ["feature 1", "feature 2", "feature 3", "feature 4", "feature 5"],
  "target_audience":    "primary customer segment in one phrase",
  "usp":                "single most compelling selling point in one sentence"
}}
""".strip()

        t0 = time.perf_counter()
        content, tok_in, tok_out = self.llm.chat([
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ])
        latency_ms = int((time.perf_counter() - t0) * 1000)

        data = json.loads(content)
        return ProductClassification(
            canonical_category = data["canonical_category"],
            product_type       = data["product_type"],
            key_features       = data["key_features"],
            target_audience    = data["target_audience"],
            usp                = data["usp"],
            model_used         = self.config.model,
            latency_ms         = latency_ms,
        )

    # ── Step 2 ─────────────────────────────────────────────────────────────────

    def generate_title(
        self,
        product: SupplierProduct,
        classification: ProductClassification,
    ) -> ProductTitle:
        prompt = f"""
Write an SEO-optimised product title for this item.

Product context:
  Raw supplier title: {product.raw_title}
  Product type:       {classification.product_type}
  Category:           {classification.canonical_category}
  Key features:       {", ".join(classification.key_features[:3])}
  Target audience:    {classification.target_audience}
  USP:                {classification.usp}

Rules:
- Primary title: maximum 80 characters, include the top 2 keywords customers search for
- Front-load the most important information (product type + key benefit)
- Do not use manufacturer part numbers or internal SKUs
- Provide 2 alternative title options as well

Return JSON:
{{
  "title":        "primary title (max 80 chars)",
  "alternatives": ["alternative 1", "alternative 2"]
}}
""".strip()

        t0 = time.perf_counter()
        content, tok_in, tok_out = self.llm.chat([
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ])
        latency_ms = int((time.perf_counter() - t0) * 1000)

        data = json.loads(content)
        title = data["title"]
        return ProductTitle(
            title        = title,
            alternatives = data.get("alternatives", []),
            char_count   = len(title),
            model_used   = self.config.model,
            latency_ms   = latency_ms,
        )

    # ── Step 3 ─────────────────────────────────────────────────────────────────

    def generate_description(
        self,
        product: SupplierProduct,
        classification: ProductClassification,
        title: ProductTitle,
    ) -> ProductDescription:
        prompt = f"""
Write the customer-facing product description for this item.

Product:
  Title:           {title.title}
  Type:            {classification.product_type}
  Category:        {classification.canonical_category}
  Key features:    {", ".join(classification.key_features)}
  Target audience: {classification.target_audience}
  USP:             {classification.usp}
  Raw specs:       {product.specs}

Requirements:
- Headline: one punchy hook line, max 120 characters, benefit-focused not spec-focused
- Body: 2-3 paragraphs (150-250 words total), conversational but informative, no jargon
- Bullets: exactly 5 feature bullets, each starting with an action word or key noun
- Write for the target audience; avoid superlatives without evidence
- Do NOT mention price

Return JSON:
{{
  "headline": "hook line (max 120 chars)",
  "body":     "2-3 paragraph description",
  "bullets":  ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5"]
}}
""".strip()

        t0 = time.perf_counter()
        content, tok_in, tok_out = self.llm.chat([
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ])
        latency_ms = int((time.perf_counter() - t0) * 1000)

        data = json.loads(content)
        return ProductDescription(
            headline   = data["headline"],
            body       = data["body"],
            bullets    = data["bullets"],
            model_used = self.config.model,
            latency_ms = latency_ms,
        )

    # ── Step 4 ─────────────────────────────────────────────────────────────────

    def generate_seo_meta(
        self,
        product: SupplierProduct,
        classification: ProductClassification,
        title: ProductTitle,
        description: ProductDescription,
    ) -> SEOMeta:
        prompt = f"""
Write the SEO meta fields for this product page.

Product:
  Title:       {title.title}
  Category:    {classification.canonical_category}
  Headline:    {description.headline}
  Key features: {", ".join(classification.key_features)}
  Target audience: {classification.target_audience}

Rules:
- Meta title: max 60 characters, include primary keyword near the front
- Meta description: max 160 characters, include a call-to-action, mention a key benefit
- Keywords: 8-10 search terms customers would actually use (mix of head and long-tail)

Return JSON:
{{
  "meta_title":       "meta title (max 60 chars)",
  "meta_description": "meta description (max 160 chars)",
  "keywords":         ["keyword1", "keyword2", ..., "keyword10"]
}}
""".strip()

        t0 = time.perf_counter()
        content, tok_in, tok_out = self.llm.chat([
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ])
        latency_ms = int((time.perf_counter() - t0) * 1000)

        data = json.loads(content)
        return SEOMeta(
            meta_title        = data["meta_title"],
            meta_description  = data["meta_description"],
            keywords          = data["keywords"],
            model_used        = self.config.model,
            latency_ms        = latency_ms,
        )

    # ── Orchestrator ───────────────────────────────────────────────────────────

    def process(self, product: SupplierProduct) -> PipelineResult:
        """Run all four steps for a single product. Returns a PipelineResult."""
        result     = PipelineResult(product=product)
        t_start    = time.perf_counter()

        log.info(f"Processing {product.sku}: {product.raw_title!r}")

        try:
            log.debug(f"  [1/4] classify_product")
            result.classification = self.classify_product(product)

            log.debug(f"  [2/4] generate_title")
            result.title = self.generate_title(product, result.classification)

            log.debug(f"  [3/4] generate_description")
            result.description = self.generate_description(
                product, result.classification, result.title
            )

            log.debug(f"  [4/4] generate_seo_meta")
            result.seo_meta = self.generate_seo_meta(
                product, result.classification, result.title, result.description
            )

        except json.JSONDecodeError as e:
            result.error = f"JSON parse error: {e}"
            log.error(f"  {product.sku} — JSON parse error: {e}")
        except httpx.HTTPStatusError as e:
            result.error = f"API error {e.response.status_code}: {e.response.text[:200]}"
            log.error(f"  {product.sku} — API error: {result.error}")
        except Exception as e:
            result.error = str(e)
            log.error(f"  {product.sku} — Unexpected error: {e}")

        result.total_latency_ms = int((time.perf_counter() - t_start) * 1000)
        status = "✓" if result.success else f"✗ {result.error}"
        log.info(f"  {product.sku} — {status}  ({result.total_latency_ms}ms)")
        return result

    def close(self):
        self.llm.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Sample product catalogue ───────────────────────────────────────────────────

SAMPLE_PRODUCTS = [
    SupplierProduct(
        sku="SUP-7743",
        raw_title="Bluetooth Headphones BH200 Black",
        specs="40mm drivers, Active Noise Cancellation, 30h battery, USB-C charging, foldable, multipoint pairing (2 devices), built-in mic, 250g",
        supplier_category="Audio/Headphones",
        cost_price=45.00,
        brand="SoundCore",
    ),
    SupplierProduct(
        sku="SUP-8812",
        raw_title="15W Fast Wireless Charger Pad",
        specs="15W Qi2 certified, compatible iPhone 12+/Samsung Galaxy S21+/AirPods, LED indicator, anti-slip surface, overheat protection, 1m braided cable included",
        supplier_category="Mobile Accessories/Chargers",
        cost_price=18.50,
    ),
    SupplierProduct(
        sku="SUP-9301",
        raw_title="Men's Trail Running Shoes Size Range",
        specs="Gore-Tex waterproof upper, Vibram outsole, 8mm drop, 28mm stack height, reflective details, sizes UK6-13, colours: grey/orange, navy/yellow",
        supplier_category="Footwear/Athletic",
        cost_price=62.00,
        brand="TrailPro",
    ),
    SupplierProduct(
        sku="SUP-4421",
        raw_title="Smart Watch Fitness Tracker SW50",
        specs="1.8in AMOLED display, heart rate, SpO2, sleep tracking, GPS, 5ATM waterproof, 7-day battery, 120 workout modes, iOS/Android",
        supplier_category="Wearables/Smartwatches",
        cost_price=89.00,
    ),
    SupplierProduct(
        sku="SUP-6634",
        raw_title="Pour Over Coffee Maker Set",
        specs="Borosilicate glass dripper, 600ml carafe, stainless steel filter (reusable), silicone grip, dishwasher safe, BPA free, serves 1-4 cups",
        supplier_category="Kitchen/Coffee Equipment",
        cost_price=24.00,
    ),
    SupplierProduct(
        sku="SUP-2290",
        raw_title="Merino Wool Crew Neck Jumper",
        specs="100% Merino wool, 18.5 micron, machine washable, sizes XS-XXL, colours: charcoal, navy, forest green, oatmeal, ribbed cuffs and hem",
        supplier_category="Clothing/Knitwear",
        cost_price=38.00,
    ),
    SupplierProduct(
        sku="SUP-5517",
        raw_title="Non-Slip Yoga Mat 6mm",
        specs="TPE foam, 183x61cm, 6mm thickness, natural rubber grip bottom, alignment lines, carrying strap included, sweat-resistant, vegan",
        supplier_category="Sports/Yoga",
        cost_price=22.00,
    ),
    SupplierProduct(
        sku="SUP-3308",
        raw_title="Hyaluronic Acid Serum 30ml",
        specs="2% Hyaluronic Acid, Vitamin B5, fragrance-free, vegan, cruelty-free, suitable for all skin types including sensitive, dermatologist tested, 30ml dropper bottle",
        supplier_category="Beauty/Skincare",
        cost_price=12.00,
    ),
    SupplierProduct(
        sku="SUP-7719",
        raw_title="LED Desk Lamp USB-C",
        specs="5 brightness levels, 3 colour temperatures (warm/neutral/cool), touch control, USB-C pass-through charging port, flexible gooseneck, memory function, eye-care certification",
        supplier_category="Lighting/Desk",
        cost_price=28.00,
    ),
    SupplierProduct(
        sku="SUP-1145",
        raw_title="Resistance Bands Set 5-Pack",
        specs="Natural latex, 5 resistance levels (10/20/30/40/50 lb), 208cm loop bands, anti-snap design, includes mesh carry bag and exercise guide",
        supplier_category="Fitness/Equipment",
        cost_price=15.00,
    ),
]


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="StyleForge product content pipeline")
    parser.add_argument("--sku",      help="Process only this SKU")
    parser.add_argument("--dry-run",  action="store_true", help="Validate config and exit")
    parser.add_argument("--model",    default="gpt-3.5-turbo", help="Override model")
    parser.add_argument("--output",   help="Write results to this JSON file")
    args = parser.parse_args()

    config = PipelineConfig(model=args.model)

    if args.dry_run:
        try:
            config.validate()
            print(f"✓ Config valid. Model: {config.model}")
        except EnvironmentError as e:
            print(f"✗ {e}")
            sys.exit(1)
        return

    config.validate()

    products = SAMPLE_PRODUCTS
    if args.sku:
        products = [p for p in products if p.sku == args.sku]
        if not products:
            print(f"SKU not found: {args.sku}")
            sys.exit(1)

    results  = []
    passed   = 0

    print(f"\nStyleForge Product Content Pipeline")
    print(f"Model: {config.model}  |  {len(products)} product(s)\n")
    print("─" * 60)

    with ProductContentPipeline(config) as pipeline:
        for product in products:
            result = pipeline.process(product)
            results.append(result)
            if result.success:
                passed += 1
                print(f"  ✓  {product.sku}  —  {result.title.title!r}")
                print(f"       {result.total_latency_ms}ms")
            else:
                print(f"  ✗  {product.sku}  —  ERROR: {result.error}")

    print("─" * 60)
    print(f"\n  {passed}/{len(products)} products processed successfully")

    if args.output:
        output = []
        for r in results:
            if r.success:
                output.append({
                    "sku":            r.product.sku,
                    "title":          r.title.title,
                    "headline":       r.description.headline,
                    "body":           r.description.body,
                    "bullets":        r.description.bullets,
                    "meta_title":     r.seo_meta.meta_title,
                    "meta_desc":      r.seo_meta.meta_description,
                    "keywords":       r.seo_meta.keywords,
                    "category":       r.classification.canonical_category,
                    "latency_ms":     r.total_latency_ms,
                })
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results written to {args.output}")


if __name__ == "__main__":
    main()
