"""
Forkmark Retail Demo — Customer Support Ticket Processing Pipeline
====================================================================

This demo shows Forkmark's core value: run the SAME multi-step AI workflow
with two model configurations across a batch of real retail tickets, automatically
score every output for divergence, and build a prioritised review queue.

WORKFLOW (4 steps per ticket):
  Step 1 │ Intent Classification   — what is this ticket about?
  Step 2 │ Sentiment Analysis      — how is the customer feeling?
  Step 3 │ Response Drafting       — write the customer-facing reply
  Step 4 │ Escalation Scoring      — does a human need to take over?

BRANCH A (Baseline):  GPT-4o-mini  @ temp 0.3  ← current production model
BRANCH B (Challenger): GPT-4o      @ temp 0.3  ← proposed upgrade

TEST SET: 15 realistic retail tickets covering refunds, shipping delays,
          product defects, account issues, VIP escalations, and edge cases.

RUN THIS DEMO:
  1. Start the Forkmark backend:   cd forkmark && uvicorn backend.main:app --reload
  2. Install deps:                  pip install httpx
  3. Run:                           python retail_pipeline.py

  Add --live to use real OpenAI API (set OPENAI_API_KEY env var):
                                    python retail_pipeline.py --live

After the run, open http://localhost:5173 to see the divergence dashboard,
prioritised review queue, and histogram. Click any comparison to see the
step-by-step diff and record your decision.
"""

import sys
import os
import json
import time
import random
import argparse
import textwrap
import httpx
from typing import List, Dict, Any, Optional

# ─── SDK import ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_DIR    = os.path.join(SCRIPT_DIR, "../../sdk")
if os.path.isdir(SDK_DIR):
    sys.path.insert(0, os.path.abspath(SDK_DIR))

try:
    import forkmark
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# ─── Configuration ────────────────────────────────────────────────────────────
FORKMARK_URL = os.environ.get("FORKMARK_URL", "http://localhost:7700")
FORKMARK_API_KEY = os.environ.get("FORKMARK_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

WORKFLOW_NAME = "retail-support-pipeline"
EVAL_RUN_NAME = "GPT-4o-mini vs GPT-4o — Customer Support Triage"
EVAL_RUN_DESC = (
    "Evaluating whether upgrading from GPT-4o-mini to GPT-4o improves "
    "response quality, escalation accuracy, and sentiment detection "
    "across our retail customer support pipeline."
)

BRANCH_A = {"label": "GPT-4o-mini (Baseline)", "model_id": "gpt-4o-mini", "temperature": 0.3}
BRANCH_B = {"label": "GPT-4o (Challenger)",    "model_id": "gpt-4o",      "temperature": 0.3}

# ─── Test cases (15 realistic retail tickets) ─────────────────────────────────
TEST_CASES = [
    {
        "label": "angry-late-delivery",
        "customer_id": "C-88234",
        "tier": "standard",
        "ticket_id": "TKT-001",
        "channel": "email",
        "text": (
            "I ordered a birthday gift for my daughter two weeks ago "
            "(order #ORD-77812) and it STILL hasn't arrived. Her birthday "
            "was yesterday and I'm absolutely furious. Your website said "
            "3-5 business days. This is completely unacceptable. I want a "
            "full refund AND compensation for the ruined birthday."
        ),
    },
    {
        "label": "wrong-item-received",
        "customer_id": "C-44501",
        "tier": "standard",
        "ticket_id": "TKT-002",
        "channel": "chat",
        "text": (
            "Hi, I received my order today but it's the completely wrong item. "
            "I ordered a blue medium t-shirt (SKU: TS-BLU-M) and received a "
            "green XL. The packing slip shows my correct order so the warehouse "
            "must have mixed it up. Can you send the right item ASAP and "
            "arrange pickup of the wrong one?"
        ),
    },
    {
        "label": "vip-damaged-product",
        "customer_id": "C-10029",
        "tier": "vip",
        "ticket_id": "TKT-003",
        "channel": "email",
        "text": (
            "This is my third order this year and I've always been happy, "
            "but my latest delivery arrived with the item visibly damaged — "
            "the box was crushed and the product inside has a crack. I've "
            "attached photos. Given my loyalty, I'd expect this to be "
            "resolved immediately with a replacement at no extra cost."
        ),
    },
    {
        "label": "simple-tracking-query",
        "customer_id": "C-91023",
        "tier": "standard",
        "ticket_id": "TKT-004",
        "channel": "chat",
        "text": (
            "Hey, just wondering where my order is? Placed it 4 days ago "
            "(order #ORD-88901). Tracking link isn't updating — "
            "still shows 'label created'. Thanks"
        ),
    },
    {
        "label": "refund-policy-dispute",
        "customer_id": "C-56778",
        "tier": "standard",
        "ticket_id": "TKT-005",
        "channel": "email",
        "text": (
            "I want to return a jacket I bought 32 days ago. Your website "
            "says 30-day returns but I've been ill and couldn't get to the "
            "post office. This is really unreasonable given the circumstances. "
            "Can you make an exception? The item is unused with all tags attached."
        ),
    },
    {
        "label": "subscription-cancel-urgent",
        "customer_id": "C-23344",
        "tier": "premium",
        "ticket_id": "TKT-006",
        "channel": "email",
        "text": (
            "I need to cancel my subscription IMMEDIATELY. I was charged again "
            "today even though I thought I cancelled last month. I have NOT "
            "authorised this charge. Please cancel the subscription, refund "
            "the unauthorised charge to my card ending 4821, and confirm in writing."
        ),
    },
    {
        "label": "product-quality-complaint",
        "customer_id": "C-67890",
        "tier": "standard",
        "ticket_id": "TKT-007",
        "channel": "email",
        "text": (
            "The blender I bought three months ago has stopped working. The "
            "motor makes a grinding noise and then cuts out. It's still under "
            "the one-year warranty. I use it daily for smoothies so this is "
            "really inconvenient. Please tell me how to get a replacement or repair."
        ),
    },
    {
        "label": "duplicate-charge",
        "customer_id": "C-34521",
        "tier": "standard",
        "ticket_id": "TKT-008",
        "channel": "chat",
        "text": (
            "I've been charged twice for the same order! My statement shows "
            "two charges of £47.99 on the same day for order #ORD-99312. "
            "This is a financial error that needs to be fixed right away. "
            "Please refund the duplicate charge."
        ),
    },
    {
        "label": "missing-item-partial",
        "customer_id": "C-78123",
        "tier": "standard",
        "ticket_id": "TKT-009",
        "channel": "email",
        "text": (
            "My order arrived today but one item is missing. I ordered "
            "3 items but only 2 were in the box. The missing item is "
            "the Aromatherapy Candle Set (SKU: ACS-003). The packing "
            "slip does list all 3 items. Please send the missing item."
        ),
    },
    {
        "label": "account-locked-unable-to-order",
        "customer_id": "C-11230",
        "tier": "premium",
        "ticket_id": "TKT-010",
        "channel": "email",
        "text": (
            "My account seems to be locked. I tried logging in three times "
            "and now it's saying 'account suspended'. I haven't done anything "
            "wrong — I've been a customer for 5 years. I need to place an "
            "urgent order for a client gift. Please unlock my account immediately."
        ),
    },
    {
        "label": "threat-legal-action",
        "customer_id": "C-44892",
        "tier": "standard",
        "ticket_id": "TKT-011",
        "channel": "email",
        "text": (
            "I have now contacted you FOUR TIMES about my missing refund "
            "for order #ORD-65500. It has been 6 weeks. If I do not receive "
            "my refund of £234.00 within 48 hours, I will be reporting this "
            "to Trading Standards, the Financial Ombudsman, and my bank for "
            "a chargeback. This is your final notice."
        ),
    },
    {
        "label": "positive-feedback-small-request",
        "customer_id": "C-92011",
        "tier": "standard",
        "ticket_id": "TKT-012",
        "channel": "chat",
        "text": (
            "Just wanted to say your service is usually great! Quick question — "
            "can I change the delivery address on my current order #ORD-10234? "
            "It hasn't shipped yet. New address is 22 Park Lane, London, SW1A 1AA."
        ),
    },
    {
        "label": "bulk-order-issue",
        "customer_id": "C-50001",
        "tier": "business",
        "ticket_id": "TKT-013",
        "channel": "email",
        "text": (
            "We placed a bulk order of 200 units (PO: B-22934) for our "
            "company event next Friday. We've just noticed the order "
            "confirmation shows the wrong product variant (black instead of "
            "white). Given the volume and tight deadline, we need urgent "
            "confirmation this can be corrected. Our account manager is "
            "unavailable. Please escalate."
        ),
    },
    {
        "label": "allergy-safety-concern",
        "customer_id": "C-83720",
        "tier": "standard",
        "ticket_id": "TKT-014",
        "channel": "email",
        "text": (
            "I ordered your 'Natural Face Cream' (SKU: NFC-200) and I am "
            "very concerned — I had an allergic reaction after using it. "
            "The ingredients listed online do NOT match the label on the "
            "product I received. I believe there is a mislabelling issue. "
            "I'm fine now but this is a serious safety concern and I want "
            "to know what you're going to do about it."
        ),
    },
    {
        "label": "sizing-exchange-simple",
        "customer_id": "C-71445",
        "tier": "standard",
        "ticket_id": "TKT-015",
        "channel": "chat",
        "text": (
            "Hi! The jeans I ordered are a bit too small. Can I exchange "
            "them for the next size up? Order #ORD-55009. They're unworn "
            "with tags. Happy to post them back."
        ),
    },
]


# ─── Mock LLM (no API key required) ──────────────────────────────────────────
class MockLLM:
    """
    Simulates two LLMs with realistically different output styles.

    GPT-4o-mini: concise, template-driven, lower empathy, sometimes
                 misses nuance on complex tickets.
    GPT-4o:      verbose, empathetic, context-aware, catches edge cases
                 (safety concerns, legal threats, VIP signals).

    Divergence is highest on:
      - Response drafting (very different tone/length)
      - Escalation scoring (GPT-4o catches more edge cases)
    """

    # Map from ticket label to model-specific outputs for each step
    _INTENT = {
        "angry-late-delivery":          ("ORDER_TRACKING > late_delivery",  "ORDER_TRACKING > significantly_late_delivery | gift_context | compensation_requested"),
        "wrong-item-received":          ("FULFILMENT_ERROR > wrong_item",   "FULFILMENT_ERROR > wrong_item | sku_mismatch | requires_pickup_coordination"),
        "vip-damaged-product":          ("PRODUCT_QUALITY > damaged_item",  "PRODUCT_QUALITY > damaged_on_delivery | vip_loyalty_context | photo_evidence"),
        "simple-tracking-query":        ("ORDER_TRACKING",                  "ORDER_TRACKING > stale_label | potential_carrier_delay"),
        "refund-policy-dispute":        ("RETURNS > policy_exception_req",  "RETURNS > policy_exception_request | mitigating_circumstances"),
        "subscription-cancel-urgent":   ("BILLING > cancel_subscription",   "BILLING > unauthorised_charge | cancel_subscription | urgent | written_confirmation_required"),
        "product-quality-complaint":    ("WARRANTY > product_failure",      "WARRANTY > product_failure | within_warranty | daily_use_impact"),
        "duplicate-charge":             ("BILLING > duplicate_charge",      "BILLING > duplicate_charge | financial_error | requires_immediate_resolution"),
        "missing-item-partial":         ("FULFILMENT_ERROR > missing_item", "FULFILMENT_ERROR > partial_delivery | sku_identified"),
        "account-locked-unable-to-order": ("ACCOUNT > locked",             "ACCOUNT > suspended_incorrectly | long_term_customer | urgent_business_need"),
        "threat-legal-action":          ("COMPLAINT > refund_overdue",      "COMPLAINT > escalation_risk | legal_threat | financial_ombudsman | chargeback_risk | 6wk_delay"),
        "positive-feedback-small-request": ("ORDER_MODIFICATION > address", "ORDER_MODIFICATION > address_change | positive_context | pre_dispatch"),
        "bulk-order-issue":             ("FULFILMENT_ERROR > wrong_variant", "FULFILMENT_ERROR > bulk_order_variant_error | event_deadline | business_account | escalation_needed"),
        "allergy-safety-concern":       ("PRODUCT_QUALITY > allergy",       "SAFETY_INCIDENT > allergic_reaction | ingredient_mislabelling | regulatory_risk | urgent"),
        "sizing-exchange-simple":       ("RETURNS > size_exchange",         "RETURNS > size_exchange | straightforward | unworn | tags_attached"),
    }

    _SENTIMENT = {
        "angry-late-delivery":          ("Angry / Frustrated",   "Highly frustrated (8/10) — missed birthday deadline creates high emotional stakes; tone is accusatory. Compensation expectation set explicitly."),
        "wrong-item-received":          ("Mildly frustrated",    "Mildly frustrated (4/10) — pragmatic tone, not aggressive. Wants resolution not confrontation. Cooperative."),
        "vip-damaged-product":          ("Disappointed",         "Disappointed (5/10) — leveraging loyalty history as social proof. Expectation of premium treatment without explicit threat."),
        "simple-tracking-query":        ("Neutral / Curious",    "Neutral (2/10) — casual, patient tone. Low urgency. Simple enquiry."),
        "refund-policy-dispute":        ("Frustrated",           "Frustrated (5/10) — feels rules are unfair given circumstances. Appeals to empathy. Non-aggressive but firm."),
        "subscription-cancel-urgent":   ("Urgent / Angry",       "Angry (7/10) — financial grievance with explicit urgency. Expects documented confirmation. Tone is assertive."),
        "product-quality-complaint":    ("Neutral / Concerned",  "Mildly frustrated (4/10) — inconvenienced but measured. Aware of warranty rights. Expects process clarity."),
        "duplicate-charge":             ("Urgent / Concerned",   "Concerned (6/10) — financial error language ('this is a mistake'). Wants speed over apology."),
        "missing-item-partial":         ("Neutral",              "Neutral (3/10) — factual and methodical. Has the evidence ready. Expects swift resolution."),
        "account-locked-unable-to-order": ("Frustrated / Urgent", "Frustrated (6/10) — long-term customer identity invoked. Business urgency adds pressure. Expects immediate fix."),
        "threat-legal-action":          ("Very Angry",           "Very angry (9/10) — explicit legal escalation threat after 4 failed contacts. High churn risk. Approaching breaking point."),
        "positive-feedback-small-request": ("Positive",          "Positive (1/10) — clearly satisfied customer. Simple request. High satisfaction baseline."),
        "bulk-order-issue":             ("Concerned / Urgent",   "Concerned (6/10) — business-critical situation with hard deadline. Professional tone but high stakes. Account manager absent adds risk."),
        "allergy-safety-concern":       ("Concerned / Scared",   "Fearful and concerned (7/10) — safety incident creates significant anxiety. Reporting tone is measured but serious. Regulatory language possible."),
        "sizing-exchange-simple":       ("Positive / Neutral",   "Positive (1/10) — relaxed, cooperative. Standard exchange request. No friction."),
    }

    _RESPONSE_A = {
        "angry-late-delivery": (
            "Dear Customer, We apologise for the delay with order #ORD-77812. "
            "We understand this is frustrating. We are investigating the delivery status and "
            "will update you within 24 hours. If the item cannot be delivered, we will "
            "process a full refund. We are sorry for any inconvenience caused."
        ),
        "wrong-item-received": (
            "Hi, Thank you for contacting us. We apologise for sending the wrong item. "
            "We will arrange for the correct blue medium t-shirt to be sent and will "
            "organise a collection of the incorrect item. Please expect a follow-up "
            "email with the collection details. Sorry for the inconvenience."
        ),
        "vip-damaged-product": (
            "Dear Customer, We are sorry to hear your item arrived damaged. Please "
            "send photos to our returns team and we will process a replacement. "
            "Thank you for your continued custom."
        ),
        "simple-tracking-query": (
            "Hi, Your tracking is showing 'label created' which means it is with "
            "our dispatch team. It should update within 1-2 business days. "
            "If it does not update, please contact us again. Thanks."
        ),
        "refund-policy-dispute": (
            "Dear Customer, Our return policy is 30 days. As your return is outside "
            "this window, we are unable to process it. We apologise for any inconvenience "
            "and encourage you to review our returns policy on our website."
        ),
        "subscription-cancel-urgent": (
            "Dear Customer, We have cancelled your subscription and will process a "
            "refund for the recent charge. This may take 3-5 business days to appear "
            "on your statement. We apologise for the inconvenience."
        ),
        "product-quality-complaint": (
            "Dear Customer, We are sorry to hear your blender has stopped working. "
            "As it is within warranty, please complete our online warranty claim form. "
            "Once approved, we will arrange a repair or replacement. Apologies for the disruption."
        ),
        "duplicate-charge": (
            "Hi, We are sorry about the duplicate charge. We have identified the error "
            "and will refund £47.99 to your account. This may take 3-5 business days. "
            "Apologies for the inconvenience."
        ),
        "missing-item-partial": (
            "Dear Customer, We are sorry the Aromatherapy Candle Set was missing from "
            "your order. We will dispatch a replacement as soon as possible. "
            "You will receive a shipping confirmation by email."
        ),
        "account-locked-unable-to-order": (
            "Dear Customer, We are sorry your account has been locked. Please verify "
            "your identity by clicking the link we have sent to your registered email "
            "address. Once verified, your account will be unlocked within 2 hours."
        ),
        "threat-legal-action": (
            "Dear Customer, We sincerely apologise for the delay in processing your "
            "refund. We take this matter seriously and have escalated it to our "
            "finance team for urgent review. You will be contacted within 48 hours."
        ),
        "positive-feedback-small-request": (
            "Hi, Thank you for your kind words! We have updated the delivery address "
            "for order #ORD-10234 to 22 Park Lane, London, SW1A 1AA. "
            "You will receive an updated confirmation shortly."
        ),
        "bulk-order-issue": (
            "Dear Customer, We have received your query about order B-22934. "
            "We are checking the order details and will contact you with an update. "
            "We understand there is a deadline and will work to resolve this quickly."
        ),
        "allergy-safety-concern": (
            "Dear Customer, We are very sorry to hear about your allergic reaction. "
            "Please stop using the product immediately. We are investigating the "
            "labelling discrepancy you have reported. Please return the product "
            "for a full refund."
        ),
        "sizing-exchange-simple": (
            "Hi, No problem! We can exchange the jeans for the next size up. "
            "Please use our online returns portal to initiate the exchange. "
            "Once we receive the return, we will dispatch the new size."
        ),
    }

    _RESPONSE_B = {
        "angry-late-delivery": (
            "Dear [Customer Name], I completely understand how upsetting it must be "
            "that your daughter's birthday gift didn't arrive in time — I'm truly sorry. "
            "I've flagged order #ORD-77812 as urgent and am personally checking with "
            "our carrier right now. In the meantime, I've authorised an immediate full "
            "refund regardless of the delivery outcome, plus a £15 gift voucher as a "
            "gesture of goodwill for the distress caused. You'll receive both "
            "confirmations by email within the hour. I'm sorry we let you and your "
            "daughter down on such an important day."
        ),
        "wrong-item-received": (
            "Hi [Customer Name], I'm so sorry — receiving the completely wrong item "
            "is really frustrating, especially when the packing slip shows your correct "
            "order. I've arranged for your blue medium t-shirt (SKU: TS-BLU-M) to be "
            "dispatched to you today on express delivery at no cost, and I've scheduled "
            "a courier to collect the incorrect green XL from your address — you won't "
            "need to do anything. You'll get tracking details for the new delivery and "
            "a collection slot confirmation within 2 hours. Really sorry for the mix-up."
        ),
        "vip-damaged-product": (
            "Dear [Customer Name], I'm really sorry your order arrived damaged — "
            "that's simply not the experience a loyal customer of three years deserves. "
            "Thank you for attaching the photos; I can clearly see the damage. I've "
            "immediately authorised an express replacement at no cost, which will be "
            "dispatched today. I've also arranged for a prepaid returns label to be "
            "emailed to you for the damaged item — no need to chase. As a token of "
            "our appreciation for your loyalty, I've added a £20 credit to your account. "
            "You'll see the replacement tracking and credit confirmation shortly."
        ),
        "simple-tracking-query": (
            "Hi [Customer Name]! Your order is on its way — the 'label created' status "
            "means it's been handed to our carrier but they haven't scanned it into their "
            "system yet. This is normal within the first 1-2 business days after dispatch. "
            "If your tracking hasn't updated by [date + 2 business days], please reply "
            "here and I'll investigate further straight away. Thanks for your patience!"
        ),
        "refund-policy-dispute": (
            "Dear [Customer Name], I'm sorry to hear you've been unwell — that's never "
            "easy. While our standard policy is 30 days, the circumstances you've "
            "described — illness preventing you from posting — are exactly the kind of "
            "situation we use our goodwill discretion for. I've approved a one-time "
            "policy exception for your return. Please use the prepaid label I've emailed "
            "you and we'll process your refund as soon as the item arrives back with us, "
            "provided it's unused with tags. I hope you're feeling better."
        ),
        "subscription-cancel-urgent": (
            "Dear [Customer Name], I completely understand your frustration — being "
            "charged unexpectedly is alarming, and I want to resolve this right away. "
            "I've cancelled your subscription effective immediately and have raised an "
            "urgent refund request for the charge to your card ending 4821. Refunds "
            "typically take 3-5 business days, but I've marked this as priority. "
            "I'm also sending you a formal cancellation confirmation and refund receipt "
            "to your registered email address now, as requested. Again, I sincerely "
            "apologise for the distress this has caused."
        ),
        "product-quality-complaint": (
            "Dear [Customer Name], I'm really sorry your blender has developed a fault "
            "— especially since you rely on it daily. The grinding noise you've described "
            "sounds like a motor bearing issue, which is a known fault covered under "
            "warranty. I don't want to put you through a lengthy claims process, so "
            "I've pre-approved a like-for-like replacement to be dispatched to you this "
            "week. I'll email you a prepaid returns label for the faulty unit — there's "
            "no need to send it back before the replacement arrives. You should receive "
            "your new blender within 3-5 business days."
        ),
        "duplicate-charge": (
            "Hi [Customer Name], I can see exactly what's happened here — there was a "
            "double-authorisation on order #ORD-99312 that resulted in two charges of "
            "£47.99. This is a financial error on our end and I'm really sorry. I've "
            "raised an urgent refund for the duplicate £47.99 to your card — this will "
            "appear within 3-5 business days, but I've flagged it as priority. I'm "
            "also sending you a written confirmation of the duplicate charge and the "
            "refund for your records. Please don't hesitate to reach out if it hasn't "
            "cleared by then."
        ),
        "missing-item-partial": (
            "Dear [Customer Name], I'm sorry your Aromatherapy Candle Set (SKU: ACS-003) "
            "wasn't in your parcel — the packing slip confirms it should have been, so "
            "this was an error on our side. I've arranged for a replacement to be "
            "dispatched to you today, and you'll receive a shipping confirmation "
            "by email shortly. No action is required on your part. Thank you for "
            "letting us know and sorry for the inconvenience."
        ),
        "account-locked-unable-to-order": (
            "Dear [Customer Name], I'm so sorry you've been locked out — especially as "
            "a customer of 5 years, this is the last thing you should be dealing with. "
            "I've reviewed your account and can see it was flagged by an automated "
            "security system — it should not have been. I've manually unlocked it right "
            "now, so you should be able to log in immediately. I've also added a note "
            "to your account to prevent this from happening again. For your urgent order, "
            "if you encounter any issues placing it, please reply here and I'll process "
            "it directly for you. Again, I'm truly sorry for the disruption."
        ),
        "threat-legal-action": (
            "Dear [Customer Name], I want to start by sincerely apologising — four "
            "contacts over six weeks without resolution is a complete failure on our part, "
            "and your frustration is entirely justified. I have escalated your refund of "
            "£234.00 to our Senior Finance Manager as an emergency case, with a personal "
            "commitment that this will be resolved within 24 hours, not 48. I am also "
            "logging a formal complaint on your behalf and will send you the reference "
            "number and the name of the Finance Manager handling this within the hour. "
            "I understand you are considering regulatory action — that is your right, "
            "and I want to do everything possible to make this right before it comes "
            "to that. You will hear from me personally by end of business today."
        ),
        "positive-feedback-small-request": (
            "Hi [Customer Name], Thank you so much — we really appreciate you taking "
            "the time to say that! I've updated the delivery address for order #ORD-10234 "
            "to 22 Park Lane, London, SW1A 1AA — all sorted. You'll receive an updated "
            "order confirmation shortly. Looking forward to your next order!"
        ),
        "bulk-order-issue": (
            "Dear [Customer Name], Thank you for flagging this — I can see the urgency "
            "given your event on Friday. I've immediately raised this as a priority case "
            "with our warehouse team to check whether the variant can be corrected before "
            "dispatch. Given the volume (200 units) and the tight deadline, I'm escalating "
            "this to our Business Accounts team right now and one of our senior "
            "representatives will contact you within 2 hours with a confirmed resolution. "
            "Please accept our apologies for the variant error — we understand the "
            "importance of this event to your organisation."
        ),
        "allergy-safety-concern": (
            "Dear [Customer Name], I'm very relieved to hear you're okay, and I want "
            "to take this report extremely seriously. A discrepancy between the online "
            "ingredients list and the physical product label is a significant safety "
            "concern that I'm escalating to our Product Safety team immediately — "
            "this is not something I'm able to handle through standard support. "
            "Our Head of Quality Assurance will contact you directly within 4 hours. "
            "In the meantime, please stop using the product and keep it for potential "
            "testing. I've raised a full refund and will arrange a specialist courier "
            "to collect the item. I'm also logging this as a formal product safety "
            "incident as required by our regulatory obligations. Thank you for bringing "
            "this to our attention — your safety is our absolute priority."
        ),
        "sizing-exchange-simple": (
            "Hi [Customer Name], Of course — happy to sort that for you! I've noted "
            "the exchange request for your order #ORD-55009. Just pop them in any "
            "packaging with the prepaid returns label I've emailed you, and once we "
            "receive them we'll get the next size dispatched straight away. "
            "Should be with you within 3-5 days of us receiving the return. Enjoy your new jeans!"
        ),
    }

    _ESCALATION_A = {
        "angry-late-delivery":          ("Score: 6/10. Delayed delivery, customer anger, compensation demanded.", True),
        "wrong-item-received":          ("Score: 3/10. Straightforward fulfilment error, easily resolved.", False),
        "vip-damaged-product":          ("Score: 5/10. Damaged product, VIP customer. Standard replacement.", True),
        "simple-tracking-query":        ("Score: 1/10. Routine tracking query.", False),
        "refund-policy-dispute":        ("Score: 4/10. Policy exception request. May require manager approval.", False),
        "subscription-cancel-urgent":   ("Score: 7/10. Unauthorised charge, urgent cancellation.", True),
        "product-quality-complaint":    ("Score: 3/10. Standard warranty claim.", False),
        "duplicate-charge":             ("Score: 6/10. Financial error, duplicate charge.", True),
        "missing-item-partial":         ("Score: 2/10. Simple missing item, straightforward replacement.", False),
        "account-locked-unable-to-order": ("Score: 5/10. Account issue, customer cannot place order.", True),
        "threat-legal-action":          ("Score: 9/10. Legal threat, repeated failures. URGENT.", True),
        "positive-feedback-small-request": ("Score: 1/10. Address change, positive context.", False),
        "bulk-order-issue":             ("Score: 8/10. Business order, wrong variant, deadline Friday.", True),
        "allergy-safety-concern":       ("Score: 7/10. Allergic reaction, labelling issue.", True),
        "sizing-exchange-simple":       ("Score: 1/10. Routine exchange.", False),
    }

    _ESCALATION_B = {
        "angry-late-delivery":          ("Score: 7/10. Missed birthday deadline creates high emotional stakes. Customer has explicitly stated compensation expectation. Recommend senior agent review if no delivery update within 2 hours. Risk: negative social review.", True),
        "wrong-item-received":          ("Score: 3/10. Clear-cut fulfilment error with supporting evidence (SKU mismatch, correct packing slip). Automation-eligible. Low escalation risk.", False),
        "vip-damaged-product":          ("Score: 6/10. VIP tier customer (3 orders this year) with photo evidence of damage. Standard replacement insufficient — loyalty gesture required. Recommend customer retention team note.", True),
        "simple-tracking-query":        ("Score: 1/10. Pre-dispatch tracking delay, normal. No escalation needed.", False),
        "refund-policy-dispute":        ("Score: 4/10. 2-day policy overage with verifiable mitigating circumstances (illness). Recommend goodwill exception — low financial risk (single item). No human escalation required.", False),
        "subscription-cancel-urgent":   ("Score: 8/10. Unauthorised charge + explicit cancellation with written confirmation demand. Financial and legal exposure. Must be handled by senior billing agent. Do not delay — chargeback risk active.", True),
        "product-quality-complaint":    ("Score: 3/10. Warranty claim with clear fault description. Within warranty period. Standard replacement flow. No escalation needed.", False),
        "duplicate-charge":             ("Score: 7/10. Confirmed financial error. Customer has documentation. Refund must be expedited — bank dispute window is typically 30 days. Finance team notification recommended.", True),
        "missing-item-partial":         ("Score: 2/10. Single item missing, SKU identified, packing slip confirms error. Automated replacement eligible. No escalation.", False),
        "account-locked-unable-to-order": ("Score: 6/10. Long-term customer (5 years) incorrectly suspended. Business urgency present. Manual unlock and account review required. Risk: churn of high-LTV customer.", True),
        "threat-legal-action":          ("Score: 10/10. CRITICAL ESCALATION REQUIRED. Customer has contacted 4 times over 6 weeks. Explicit threats: Trading Standards, Financial Ombudsman, chargeback. 6-week delay is indefensible. Assign to Senior Customer Relations Manager immediately. Do not use template responses. Financial and reputational risk is high.", True),
        "positive-feedback-small-request": ("Score: 1/10. Pre-dispatch address change. Positive customer. Automation-eligible. No escalation.", False),
        "bulk-order-issue":             ("Score: 9/10. Business account, 200-unit order with wrong variant, event deadline Friday. Account manager unavailable. Financial and reputational impact significant. Escalate to Business Accounts senior team immediately.", True),
        "allergy-safety-concern":       ("Score: 10/10. PRODUCT SAFETY INCIDENT. Allergic reaction + ingredient label discrepancy. This is a potential regulatory compliance matter (Consumer Protection Act, Cosmetic Products Regulation). Do NOT handle through standard support. Escalate to Product Safety & Quality Manager immediately. Regulatory reporting may be required. Preserve product for testing.", True),
        "sizing-exchange-simple":       ("Score: 1/10. Routine, cooperative size exchange. Automation-eligible.", False),
    }

    def call(self, messages: list, model: str, temperature: float) -> str:
        """Route to the correct mock response based on model and conversation context."""
        user_content = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
        sys_content  = " ".join(m.get("content", "") for m in messages if m.get("role") == "system")

        label = _extract_label(user_content)
        step  = _extract_step(sys_content)
        is_a  = "mini" in model

        # Small latency simulation
        time.sleep(random.uniform(0.05, 0.15))

        if step == "intent":
            pair = self._INTENT.get(label, ("OTHER", "OTHER > unclassified"))
            return pair[0] if is_a else pair[1]
        elif step == "sentiment":
            pair = self._SENTIMENT.get(label, ("Neutral", "Neutral (3/10) — no strong signals detected."))
            return pair[0] if is_a else pair[1]
        elif step == "response":
            d = self._RESPONSE_A if is_a else self._RESPONSE_B
            return d.get(label, "Thank you for contacting us. A member of our team will be in touch shortly.")
        elif step == "escalation":
            d = self._ESCALATION_A if is_a else self._ESCALATION_B
            text, _ = d.get(label, ("Score: 3/10. Standard query.", False))
            return text
        return "[mock output]"


def _extract_label(text: str) -> str:
    for case in TEST_CASES:
        if case["ticket_id"] in text or case["label"] in text:
            return case["label"]
    return ""


def _extract_step(sys_text: str) -> str:
    t = sys_text.lower()
    if "intent" in t or "classif" in t:
        return "intent"
    if "sentiment" in t or "emotion" in t or "feeling" in t:
        return "sentiment"
    if "response" in t or "reply" in t or "draft" in t:
        return "response"
    if "escalat" in t or "score" in t or "human" in t:
        return "escalation"
    return "unknown"


# ─── System prompts for each step ────────────────────────────────────────────
INTENT_PROMPT = """You are a retail customer service AI.
Classify the intent of the customer ticket below.
Output ONLY the intent label(s), nothing else.
Format: CATEGORY > sub_category | additional_signals
Examples: ORDER_TRACKING > late_delivery | compensation_requested"""

SENTIMENT_PROMPT = """You are a customer service sentiment analyser.
Analyse the emotional tone of the customer ticket below.
Output a brief sentiment label with confidence indicators.
Be specific about what signals drive your assessment."""

RESPONSE_PROMPT = """You are a senior retail customer service agent.
Write a professional, empathetic response to the customer ticket below.
Address all issues raised. Be specific, not generic.
Customer tier and context are provided in the ticket metadata."""

ESCALATION_PROMPT = """You are a customer service escalation scoring AI.
Review the ticket and output an escalation score from 1-10 and reasoning.
Format: Score: X/10. [Reasoning]
Consider: financial risk, legal exposure, customer tier, urgency, churn risk."""


# ─── Real OpenAI call ─────────────────────────────────────────────────────────
def make_openai_fn():
    """Returns a real OpenAI call function if the key is set."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        def call(messages: list, model: str, temperature: float) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=400,
            )
            return resp.choices[0].message.content.strip()
        return call
    except ImportError:
        print("[warning] openai package not installed. Using mock.")
        return None


# ─── Main pipeline runner ─────────────────────────────────────────────────────
def run_pipeline(live: bool = False):
    print("\n" + "═" * 70)
    print("  FORKMARK RETAIL DEMO — Customer Support Triage Pipeline")
    print("═" * 70)
    print(f"  Eval Run:  {EVAL_RUN_NAME}")
    print(f"  Branch A:  {BRANCH_A['label']}")
    print(f"  Branch B:  {BRANCH_B['label']}")
    print(f"  Test Cases: {len(TEST_CASES)} retail tickets")
    print(f"  Mode:      {'LIVE (OpenAI API)' if live else 'MOCK (no API key needed)'}")
    print("═" * 70 + "\n")

    # Set up LLM function
    mock_llm = MockLLM()
    if live and OPENAI_API_KEY:
        call_fn = make_openai_fn()
        if not call_fn:
            print("[warn] Falling back to mock.")
            call_fn = mock_llm.call
    else:
        call_fn = mock_llm.call
        if live and not OPENAI_API_KEY:
            print("[warn] --live flag set but OPENAI_API_KEY not found. Using mock.\n")

    # Init SDK
    if not SDK_AVAILABLE:
        print("[error] Forkmark SDK not found. Make sure you are running from the correct directory.")
        sys.exit(1)

    if not FORKMARK_API_KEY:
        print("[error] FORKMARK_API_KEY not set.")
        print("        Create a key first:")
        print("        curl -s -X POST http://127.0.0.1:7700/api/keys \\")
        print("          -H 'Content-Type: application/json' \\")
        print("          -d '{\"name\": \"demo\"}' | python -m json.tool")
        print("        Then: export FORKMARK_API_KEY=fm_...")
        sys.exit(1)

    forkmark.init(api_key=FORKMARK_API_KEY, base_url=FORKMARK_URL)

    # Run the batch eval
    with forkmark.eval_run(
        name=EVAL_RUN_NAME,
        workflow=WORKFLOW_NAME,
        description=EVAL_RUN_DESC,
        branch_a=BRANCH_A,
        branch_b=BRANCH_B,
        inputs=TEST_CASES,
    ) as er:

        print(f"[forkmark] Eval run created — ID: {er.eval_run_id}\n")

        for i, case in enumerate(er):
            label   = case.label
            meta    = f"[{case.input['tier'].upper()} | {case.input['channel']} | {case.input['ticket_id']}]"
            ticket  = case.input["text"]
            ticket_ctx = f"[ticket_id={case.input['ticket_id']}, label={label}, tier={case.input['tier']}]\n\n{ticket}"

            print(f"  [{i+1:02d}/{len(TEST_CASES)}] {label}")
            print(f"         {meta}")

            # ── STEP 1: Intent Classification ──────────────────────────────
            msgs_intent = [{"role": "user", "content": ticket_ctx}]
            intent_a = case.step(
                "intent_classification",
                model="gpt-4o-mini",
                messages=msgs_intent,
                temperature=0.1,
                system_prompt=INTENT_PROMPT,
                call_fn=call_fn,
            )
            intent_b = case.branch_step(
                "intent_classification",
                model="gpt-4o",
                messages=msgs_intent,
                temperature=0.1,
                system_prompt=INTENT_PROMPT,
                call_fn=call_fn,
            )

            # ── STEP 2: Sentiment Analysis ─────────────────────────────────
            msgs_sentiment = [{"role": "user", "content": ticket_ctx}]
            sentiment_a = case.step(
                "sentiment_analysis",
                model="gpt-4o-mini",
                messages=msgs_sentiment,
                temperature=0.2,
                system_prompt=SENTIMENT_PROMPT,
                call_fn=call_fn,
            )
            sentiment_b = case.branch_step(
                "sentiment_analysis",
                model="gpt-4o",
                messages=msgs_sentiment,
                temperature=0.2,
                system_prompt=SENTIMENT_PROMPT,
                call_fn=call_fn,
            )

            # ── STEP 3: Response Drafting ──────────────────────────────────
            draft_context = (
                f"Customer ticket: {ticket_ctx}\n\n"
                f"Intent: {intent_a}\nSentiment: {sentiment_a}"
            )
            msgs_response = [{"role": "user", "content": draft_context}]
            response_a = case.step(
                "response_drafting",
                model="gpt-4o-mini",
                messages=msgs_response,
                temperature=0.4,
                system_prompt=RESPONSE_PROMPT,
                call_fn=call_fn,
            )
            response_b = case.branch_step(
                "response_drafting",
                model="gpt-4o",
                messages=msgs_response,
                temperature=0.4,
                system_prompt=RESPONSE_PROMPT,
                call_fn=call_fn,
            )

            # ── STEP 4: Escalation Scoring ─────────────────────────────────
            escalation_context = (
                f"Ticket: {ticket_ctx}\n\n"
                f"Intent: {intent_a}\nSentiment: {sentiment_a}"
            )
            msgs_esc = [{"role": "user", "content": escalation_context}]
            esc_a = case.step(
                "escalation_scoring",
                model="gpt-4o-mini",
                messages=msgs_esc,
                temperature=0.1,
                system_prompt=ESCALATION_PROMPT,
                call_fn=call_fn,
            )
            esc_b = case.branch_step(
                "escalation_scoring",
                model="gpt-4o",
                messages=msgs_esc,
                temperature=0.1,
                system_prompt=ESCALATION_PROMPT,
                call_fn=call_fn,
            )

            # Print per-case summary
            _print_case_summary(label, intent_a, intent_b, sentiment_a, sentiment_b,
                                response_a, response_b, esc_a, esc_b)

    # Final stats
    stats = er.stats
    print("\n" + "═" * 70)
    print(f"  EVAL RUN COMPLETE")
    print(f"  ID:         {er.eval_run_id}")
    print(f"  Processed:  {stats['completed']}/{stats['total']} cases")
    if stats['failed'] > 0:
        print(f"  ⚠ Failed:  {stats['failed']} cases")
    print("═" * 70)
    print(f"\n  → Open the Forkmark dashboard to review results:")
    print(f"    http://localhost:5173\n")
    print(f"  → Or go directly to this eval run:")
    print(f"    http://localhost:5173 → Eval Runs → {EVAL_RUN_NAME}\n")
    print("  The divergence histogram will show which tickets diverged most.")
    print("  Click 'Review Next →' to work through the highest-divergence cases.")
    print("  Every decision you make is logged as preference data.\n")


def _print_case_summary(label, ia, ib, sa, sb, ra, rb, ea, eb):
    """Print a readable per-case summary showing both branch outputs."""
    from difflib import SequenceMatcher

    def div(a, b):
        import re
        wa = set(re.findall(r'\w+', a.lower()))
        wb = set(re.findall(r'\w+', b.lower()))
        j  = 1 - len(wa & wb) / (len(wa | wb) or 1)
        s  = 1 - SequenceMatcher(None, a, b).ratio()
        return round(j * 0.6 + s * 0.4, 2)

    d = div(rb, ra)  # divergence on response (most interesting step)
    bar_len = int(d * 20)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    colour = "🟢" if d < 0.2 else "🟡" if d < 0.5 else "🔴"

    print(f"         Response divergence: {colour} {bar}  {d:.0%}")
    print(f"         Intent  A: {ia[:60]}")
    print(f"         Intent  B: {ib[:60]}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Forkmark Retail Demo — Customer Support Pipeline"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Use real OpenAI API calls (requires OPENAI_API_KEY env var)"
    )
    args = parser.parse_args()
    run_pipeline(live=args.live)
