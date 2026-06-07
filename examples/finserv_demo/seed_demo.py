"""
Forkmark Financial Services Demo — Fraud Alert Explanation
============================================================

Workflow:  fraud-alert-explanation
Eval run:  Plain-Language Prompt v2 vs Technical Internal Alert v1
Branches:
  A — Plain-Language Customer Prompt v2  (baseline — wins this eval)
  B — Technical Internal Alert v1         (challenger — jargon-heavy, less actionable)

10 fraud/risk alert cases × 4 steps each:
  transaction_analysis · risk_scoring · customer_notification · action_steps

Run:   python seed_demo.py
Then:  open http://localhost:5173
"""

import httpx
import time, sys, re, os
from difflib import SequenceMatcher

BASE_URL = "http://localhost:7700"
_api_key = os.environ.get("FORKMARK_API_KEY", "")
HEADERS  = {"Content-Type": "application/json"}
if _api_key:
    HEADERS["X-API-Key"] = _api_key


def api(method, path, data=None, _retries=4, _backoff=1.0):
    url = BASE_URL + path
    for attempt in range(_retries):
        try:
            r = getattr(httpx, method)(url, json=data, headers=HEADERS, timeout=10)
            if r.status_code == 429:
                wait = _backoff * (2 ** attempt)
                print(f"  [rate-limit] backing off {wait:.1f}s before retry {attempt+1}/{_retries-1}...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            print(f"\n[error] Cannot connect to {BASE_URL}")
            print("  Make sure Forkmark is running (run run.bat first)\n")
            sys.exit(1)
        except Exception as e:
            print(f"[error] {method.upper()} {path}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  Response: {e.response.text[:200]}")
            return None
    print(f"[error] {method.upper()} {path}: rate limit retries exhausted")
    return None


CASES = [
    {
        "label": "foreign-country-transaction",
        "alert": "Transaction flagged: £342.00 at merchant 'ElectronicsPlus Lagos' in Nigeria. Cardholder account shows no prior international transactions in 36-month history. Transaction time: 02:14 local UK time. Card: Visa Debit ending 4821.",
        "ta_a": "Transaction Analysis: £342.00 charge at an electronics retailer in Lagos, Nigeria. This is the cardholder's first-ever international transaction in 3 years. Transaction occurred at 2:14am UK time, suggesting either travel or remote/online purchase. Risk indicators: new geography, unsocial hours, high-value single transaction.",
        "ta_b": "TXN_INTL_FLAG: MCC 5732, Nigeria (NG), 02:14 UTC. Velocity: 0 prior intl TXNs L36M. Amt: 342.00 GBP. Card: VISA_DB_4821. Rules triggered: GEO_NEW, TIME_OOH, AMT_THRESHOLD_MED.",
        "rs_a": "Risk Score: 72/100 (HIGH). Key factors: (1) First international transaction in 36-month history — 8× higher fraud probability for first-time foreign transactions; (2) Out-of-hours transaction time (2:14am) — associated with 34% of card-not-present fraud; (3) High-risk merchant geography. Recommendation: Soft decline and customer verification before authorisation.",
        "rs_b": "RISK_SCORE: 72. TIER: HIGH. RULES: GEO_NEW(+25), TIME_OOH(+18), MCC_ELECTRONICS(+12), HIST_INTL_0(+17). ACTION_CODE: SOFT_DECLINE_CVS.",
        "cn_a": "Dear [Cardholder Name], We've temporarily held a transaction on your Visa Debit card ending 4821. A payment of £342.00 to an electronics store in Nigeria was flagged because it's outside your normal spending pattern. If you made this purchase, please reply YES to authorise it. If you didn't make this payment, please reply NO and we'll protect your account immediately. You can also call us 24/7 on the number on the back of your card.",
        "cn_b": "ALERT: TXN_HELD. Card 4821. Amt: £342.00. Merchant: ElectronicsPlus NG. Status: PENDING_CVS. Action required: CVS verification. Reply Y/N. Ref: FRD-2024-0441.",
        "as_a": "If customer confirms: authorise transaction, add Nigeria to approved travel list, lower risk score for this merchant category for 30 days. If customer denies: immediately block card ending 4821, raise fraud claim, issue replacement card within 24 hours, initiate chargeback to merchant, notify fraud team for pattern analysis.",
        "as_b": "CVS_CONFIRM: AUTH_TXN + WL_GEO_NG + RISK_ADJ_30D. CVS_DENY: CARD_BLOCK_4821 + FRAUD_CLAIM_INIT + CARD_REISSUE_24H + CB_INIT + FRAUD_ANALYTICS_FLAG.",
    },
    {
        "label": "large-unusual-purchase",
        "alert": "Transaction flagged: £4,750.00 at 'Prestige Jewellers London' (MCC 5944). Cardholder's average monthly spend: £1,200. Largest previous single transaction: £620. Account age: 4 years. No jewellery purchases in account history.",
        "ta_a": "Transaction Analysis: £4,750 jewellery purchase — nearly 4× the cardholder's monthly spend and 7.6× their previous largest single transaction. No prior jewellery purchases in 4-year account history. This is a significant behavioural anomaly: amount, category, and merchant type are all new patterns.",
        "ta_b": "TXN_LARGE: MCC 5944 (jewellery), £4750.00 GBP. Cardholder avg monthly: £1200. Max prev single: £620.00. Rule: AMT_7X_MAX_PREV, CAT_NEW_JEWELLERY, SPEND_4X_MONTHLY.",
        "rs_a": "Risk Score: 68/100 (HIGH). Factors: (1) Transaction 7.6× cardholder's maximum prior single spend — strong behavioural outlier; (2) New merchant category (jewellery) never used in 4-year history; (3) High-value single purchase with no pattern establishment. Mitigating factor: reputable London merchant (not a grey-market seller). Recommendation: Friction step — real-time push notification requiring explicit app confirmation.",
        "rs_b": "RISK_SCORE: 68. TIER: HIGH. AMT_7X_PREV(+30), CAT_NEW(+20), SPEND_OUTLIER(+18). MITIGANT: MERCHANT_LEGIT(-5). ACTION: PUSH_NOTIF_CONFIRM.",
        "cn_a": "Hi [Cardholder Name], we've spotted a large payment that's different from your usual spending. A transaction of £4,750 at Prestige Jewellers in London has been paused for your security. Did you make this purchase? Tap 'Yes, that's me' in the app to approve it, or 'No, block it' if it wasn't you. If you approve it, we'll complete the payment right away.",
        "cn_b": "TXN_ALERT: £4750.00 MCC_5944 PRESTIGE_JEWELLERS. SPEND_ANOMALY_DETECTED. CONFIRM_IN_APP: Y/N. Ref: FRD-2024-0882.",
        "as_a": "If confirmed in app: authorise, log as confirmed high-value purchase, update spending profile. If denied: block card immediately, open fraud case, initiate chargeback. If no response within 10 minutes: auto-decline transaction and send follow-up SMS advising customer to contact us to complete purchase.",
        "as_b": "APP_Y: AUTH + PROFILE_UPDATE. APP_N: BLOCK + FRAUD_CASE + CB. NO_RESP_10M: AUTO_DECLINE + SMS_FOLLOWUP.",
    },
    {
        "label": "rapid-successive-transactions",
        "alert": "Velocity alert: 6 transactions in 8 minutes totalling £847.00. Merchants: 3 different online retailers, 1 pharmacy, 1 supermarket, 1 digital goods. All card-not-present. Cardholder's typical daily spend: £45. Account: 2 years old.",
        "ta_a": "Transaction Analysis: 6 transactions in 8 minutes, all card-not-present, across 6 entirely different merchant categories — a classic 'testing then spending' fraud pattern. Total £847 vs typical daily spend of £45 (18.8× daily average). The mix of real-goods retailers and digital goods is consistent with card details being tested at low-friction merchants before larger purchases.",
        "ta_b": "VELOCITY_ALERT: 6 TXNs / 8 min, CNP, £847.00 total. Cardholder daily avg: £45.00. Merchants: 6 distinct MCCs. Pattern: CARD_TEST_SPEND. Rules: VEL_6_8M, CNP_ALL, AMT_18X_DAILY.",
        "rs_a": "Risk Score: 91/100 (CRITICAL). Factors: (1) 6 CNP transactions in 8 minutes — highly anomalous velocity; (2) 6 entirely different merchant categories in one burst — inconsistent with genuine shopping behaviour; (3) 18.8× daily average spend in 8 minutes; (4) Digital goods purchase is a known fraud liquidation vector (instant delivery, no shipping address required). Recommendation: Immediate hard decline on all pending transactions, real-time alert to cardholder, temporary card suspension.",
        "rs_b": "RISK_SCORE: 91. TIER: CRITICAL. VEL_HIGH(+35), CNP_MULTI(+28), AMT_18X(+25), DGTL_GOODS(+10). ACTION: HARD_DECLINE_ALL + CARD_SUSPEND + URGENT_ALERT.",
        "cn_a": "URGENT: We've paused your card because we've seen 6 payments in the last 8 minutes that don't look like your normal spending. Your account security is our priority. If these were all you, please call us right now at [number] or open your app to review each transaction. If your card details have been stolen, we'll cancel your card, refund any fraudulent charges, and send you a new card within 24 hours.",
        "cn_b": "URGENT_ALERT: CARD_4821 SUSPENDED. 6 TXNs / 8 min flagged. Call [number] or app review required. FRAUD_PROT_ACTIVE. Ref: FRD-2024-1103.",
        "as_a": "Immediate actions: (1) Suspend card for new transactions; (2) Allow customer-initiated review via app or phone; (3) If customer confirms fraud: open bulk fraud claim for all 6 transactions, initiate chargebacks, issue replacement card same-day where possible; (4) Flag account for enhanced monitoring for 90 days post-resolution; (5) Escalate to fraud intelligence team — pattern may indicate compromised card data batch.",
        "as_b": "IMMED: CARD_SUSPEND. CUST_CONFIRM_FRAUD: BULK_FRAUD_CLAIM + CB_X6 + CARD_REISSUE. MONITOR_90D. ESC_FRAUD_INTEL.",
    },
    {
        "label": "new-payee-large-transfer",
        "alert": "Bank transfer flagged: £12,500 to new payee 'John Smith — Account 12-34-56 / 87654321'. Payee added and payment initiated within 4 minutes. Cardholder's largest previous transfer: £2,000. No prior payments to this sort code. Message field: 'investment opportunity'.",
        "ta_a": "Transaction Analysis: £12,500 transfer to a brand-new payee, initiated 4 minutes after the payee was added — no cooling-off period. 'Investment opportunity' in the reference is a high-risk phrase strongly associated with Authorised Push Payment (APP) fraud and investment scams. Transfer amount is 6.25× the cardholder's previous maximum. Sort code check should be performed.",
        "ta_b": "TXN_TRANSFER: £12500 to NEW_PAYEE John_Smith. Payee_added_to_payment: 4 min. Ref: 'investment opportunity'. Max prev transfer: £2000. Rules: NEW_PAYEE_IMMEDIATE, AMT_6X_MAX, REF_INVEST_FLAG.",
        "rs_a": "Risk Score: 95/100 (CRITICAL — APP Fraud Indicator). Factors: (1) New payee + immediate large payment — consistent with scam victim being manipulated in real time; (2) 'Investment opportunity' reference — matches patterns in 76% of APP investment fraud cases (UK Finance 2023 data); (3) 4-minute payee-to-payment window — far below voluntary APP fraud code recommended cooling-off periods; (4) 6.25× maximum prior transfer. Recommendation: Mandatory friction — phone call to customer before release. Potential vulnerable customer indicator.",
        "rs_b": "RISK_SCORE: 95. CRITICAL. APP_FRAUD_IND(+40), NEW_PAYEE_FAST(+25), REF_INVEST(+20), AMT_6X(+10). ACTION: MANDATORY_CALL_BEFORE_RELEASE.",
        "cn_a": "We need to speak with you before releasing this payment. We've flagged a £12,500 transfer to a new payee because investment-related payments to new accounts are frequently targeted by scammers — and we want to make sure you're protected. Please call us on [number] in the next 30 minutes, or we'll need to hold this payment. We'd rather take a few minutes now than have you lose thousands to a scam. Your money is safe while we wait for your call.",
        "cn_b": "HOLD_NOTICE: Transfer £12500 to John_Smith SUSPENDED. APP_FRAUD_REVIEW_REQUIRED. Call [number] within 30 min to release. Ref: FRD-2024-0219.",
        "as_a": "Call script focus: (1) Who introduced you to this investment? (2) Have you met them in person or only online? (3) Did they contact you first? (4) Have you verified the company on the FCA register? If customer is being coerced or answers raise red flags: advise customer to end the call with scammer, refuse payment, refer to National Cyber Security Centre. If customer insists payment is legitimate: document verbal confirmation, add vulnerability flag for review, release after 24h cooling-off period. Log all details for UK Finance APP fraud data.",
        "as_b": "CALL_SCRIPT: SCAM_VERIFY_Q1-Q4. IF_COERCION: REFUSE_PMT + NCSC_REFER. IF_CUST_INSISTS: DOC_VERBAL_CONF + VULN_FLAG + 24H_COOL_OFF. LOG_UKFINANCE.",
    },
    {
        "label": "atm-withdrawal-abroad",
        "alert": "ATM cash withdrawal: €500 at ATM in Bangkok, Thailand. Cardholder has active travel notification for France (registered 3 days ago). Account shows no prior cash withdrawals in Thailand. Current time: 03:22 local Bangkok time.",
        "ta_a": "Transaction Analysis: €500 ATM withdrawal in Bangkok at 3:22am — but cardholder registered a travel notification for France only 3 days ago. Geographic inconsistency: Bangkok and Paris are 9,400km apart with no connecting stop flagged. Out-of-hours withdrawal at 3:22am Bangkok time. Cash withdrawals at odd hours in a different country than the registered travel destination are a common indicator of card cloning or stolen card use.",
        "ta_b": "ATM_INTL: €500 Bangkok TH, 03:22. Travel_notif: France_only. Prior_TH_withdrawals: 0. Rules: GEO_MISMATCH_TRAVEL, TIME_OOH, CASH_INTL_NEW.",
        "rs_a": "Risk Score: 83/100 (HIGH). Factors: (1) Geographic mismatch with registered travel — customer said they'd be in France, card is in Thailand; (2) Out-of-hours ATM withdrawal (3:22am); (3) No prior Thailand transactions in account history; (4) Cash withdrawal (not trackable to a specific merchant). Mitigating factor: possible genuine itinerary change or multi-destination travel. Recommendation: Immediate SMS + app notification; hold further Thailand transactions pending confirmation.",
        "rs_b": "RISK_SCORE: 83. HIGH. GEO_MISMATCH(+30), TIME_OOH(+18), CASH_NEW_GEO(+22), HIST_TH_0(+13). MITIGANT: TRAVEL_NOTIF_ACTIVE(-5). ACTION: SMS_NOTIFY + HOLD_TH_TXN.",
        "cn_a": "Hi [Cardholder Name], we've seen a cash withdrawal of €500 from an ATM in Bangkok, Thailand — but your travel notification is registered for France. We want to make sure your card is safe. If you've changed your travel plans, just reply 'YES' to confirm and we'll update your account. If you're still in France and didn't make this withdrawal, please reply 'NO' and we'll act right away to protect your account. You can also call us 24/7 on the number on the back of your card.",
        "cn_b": "TXN_ALERT: €500 ATM Bangkok TH. Travel_reg: France. GEO_MISMATCH. Confirm travel change Y/N or call [number]. Ref: FRD-2024-0654.",
        "as_a": "If YES (travel change confirmed): update travel notification to include Thailand, lift hold on Thailand transactions, note account. If NO (fraudulent): block card immediately, open fraud claim for ATM withdrawal, attempt chargeback (limited for cash — document attempt), issue emergency card replacement — partner banks in Bangkok can provide emergency cash advance. Alert fraud intelligence: possible card skimming at European ATM given France travel.",
        "as_b": "CONFIRM_YES: UPDATE_TRAVEL_TH + LIFT_HOLD. CONFIRM_NO: BLOCK_CARD + FRAUD_CLAIM + CB_ATTEMPT + EMERGENCY_CARD + FRAUD_INTEL_ALERT_SKIM.",
    },
    {
        "label": "subscription-charge-spike",
        "alert": "Anomaly detected: 11 new recurring subscription charges in the past 7 days totalling £287/month. Prior subscription baseline: 3 subscriptions, £42/month. Charges from: 4 streaming services, 2 gaming platforms, 2 cloud storage, 1 VPN, 1 adult content platform, 1 unrecognised merchant.",
        "ta_a": "Transaction Analysis: Subscription charges jumped from 3 (£42/month) to 14 (£329/month) in 7 days — an 683% increase in subscription volume. The addition of 11 new subscriptions in a single week is abnormal consumer behaviour. Particularly notable: 1 adult content platform and 1 unrecognised merchant. Pattern is consistent with either: (a) account takeover — attacker using card to register subscriptions for resale/own use; or (b) family member access without authorisation.",
        "ta_b": "SUB_SPIKE: 11 new subs / 7 days. Prior: 3 subs £42/mo. New total: 14 subs £329/mo. Inc: 4_STREAM, 2_GAMING, 2_CLOUD, 1_VPN, 1_ADULT, 1_UNKNOWN. Rules: SUB_VEL_HIGH, ADULT_CONTENT_FLAG, UNKNOWN_MERCH.",
        "rs_a": "Risk Score: 77/100 (HIGH). Factors: (1) 11 new subscriptions in 7 days — 3.7× standard monthly subscription acquisition rate; (2) Account takeover indicator — attackers often register resellable streaming accounts; (3) Adult content platform and unrecognised merchant warrant separate investigation; (4) VPN subscription may indicate privacy-seeking behaviour post-account compromise. Recommendation: In-app notification showing full list of new subscriptions; customer confirmation required for each.",
        "rs_b": "RISK_SCORE: 77. HIGH. SUB_VEL_11_7D(+32), ATO_PATTERN(+25), ADULT_FLAG(+12), UNKNOWN_MERCH(+8). ACTION: IN_APP_SUB_LIST_CONFIRM.",
        "cn_a": "We've noticed 11 new subscriptions added to your account this week — that's a big change from your usual pattern. Here's a summary of the new charges: [list]. Your total subscription cost has gone from £42/month to £329/month. Do all of these look right to you? Open your app to review and confirm or cancel each one. If you didn't sign up for any of these, let us know and we'll help you dispute the charges and secure your account.",
        "cn_b": "SUB_ALERT: 11 new subs detected. New monthly total: £329. Prior: £42. Review in app. Confirm/dispute each. Ref: FRD-2024-0991.",
        "as_a": "Present customer with full itemised subscription list in-app. For each: (1) allow one-tap confirm or dispute; (2) for disputed: initiate individual chargebacks; (3) for unrecognised merchant: open fraud investigation, attempt to identify via MID lookup; (4) if majority disputed: flag for account takeover review, force password reset, check login history for unrecognised devices; (5) block further new subscription registrations for 30 days pending review.",
        "as_b": "IN_APP_LIST: ITEM_CONFIRM/DISPUTE_EACH. DISPUTED: CB_INIT_EACH. UNKNOWN_MERCH: FRAUD_INV + MID_LOOKUP. MAJORITY_DISPUTED: ATO_REVIEW + FORCE_PW_RESET + LOGIN_AUDIT. BLOCK_NEW_SUB_30D.",
    },
    {
        "label": "merchant-category-mismatch",
        "alert": "Transaction flagged: £1,200 at merchant 'Fresh Food Supplies Ltd' (MCC 5411 — Grocery Stores). Business account holder; normal grocery spend £95/month. Transaction processed as card-present. Business operates as a law firm (SIC 7411).",
        "ta_a": "Transaction Analysis: £1,200 at a grocery store on a law firm's business account — 12.6× their typical monthly grocery spend. The mismatch between the account holder's business type (law firm) and a £1,200 grocery purchase warrants investigation. Possible explanations: (a) misclassified merchant — 'Fresh Food Supplies' may be a corporate catering or events supplier; (b) card misuse by employee; (c) merchant MCC fraud (merchants sometimes mislabel to avoid interchange restrictions).",
        "ta_b": "TXN_MCC_MISMATCH: £1200, MCC_5411 (GROCERY). Account_type: BUSINESS_LEGAL. Monthly_grocery_avg: £95. Multiplier: 12.6x. Rules: MCC_BIZ_MISMATCH, AMT_12X_CAT_AVG.",
        "rs_a": "Risk Score: 62/100 (MEDIUM-HIGH). Factors: (1) 12.6× category average spend; (2) Business type vs merchant category mismatch — law firms rarely have large grocery purchases; (3) Potential MCC laundering (gambling or other restricted merchants sometimes misclassify). Mitigating factors: card-present transaction (physical card used), single transaction. Recommendation: Delayed notification — send review alert without blocking; escalate to business account manager.",
        "rs_b": "RISK_SCORE: 62. MED_HIGH. AMT_12X(+25), BIZ_MCC_MISMATCH(+22), MCC_LAUNDER_RISK(+15). MITIGANT: CP_TXN(-5), SINGLE_TXN(-5). ACTION: DELAYED_NOTIFY + BIZ_AM_ESC.",
        "cn_a": "We're checking a transaction on your business account. A payment of £1,200 to Fresh Food Supplies Ltd was flagged as it's different from your typical spending pattern. If this was for a legitimate business purpose (such as corporate catering or an event), no action is needed — just log into your account to confirm. If you didn't authorise this charge or it doesn't look right, please contact your dedicated business account manager at [number].",
        "cn_b": "BIZ_ACCT_ALERT: £1200 MCC_5411 FRESH_FOOD_SUPPLIES. MCC_MISMATCH_BIZ_TYPE. Confirm legitimate Y/N via app or call BAM [number]. Ref: FRD-2024-0773.",
        "as_a": "Escalate to business account manager with full transaction context. BAM to contact client within 2 hours. Parallel action: submit merchant MCC review request — if 'Fresh Food Supplies' is consistently triggering alerts as a law firm merchant, initiate MCC verification with acquiring bank. If client confirms fraudulent: standard fraud claim + chargeback. If client confirms legitimate but MCC is wrong: request merchant to resubmit with correct MCC for accurate expense reporting.",
        "as_b": "ESC_BAM_2H. PARALLEL: MCC_REVIEW_REQ. FRAUD_CONFIRM: FRAUD_CLAIM + CB. LEGIT_MCC_WRONG: REQUEST_RESUBMIT_CORRECT_MCC.",
    },
    {
        "label": "dormant-account-activity",
        "alert": "Activity detected on dormant account. Account last used: 14 months ago. New activity: online login from IP 185.220.101.x (Tor exit node), £800 bank transfer initiated to new payee, password changed 2 hours before transaction.",
        "ta_a": "Transaction Analysis: Dormant account reactivated via Tor exit node, password changed, then £800 transfer to new payee — all within a 2-hour window. This is a textbook account takeover (ATO) pattern: attacker gained credentials (likely via phishing or data breach), changed password to lock out the real owner, then immediately initiated a transfer. The Tor IP is a high-confidence fraud indicator — legitimate customers very rarely access banking via Tor.",
        "ta_b": "ATO_ALERT: DORMANT_ACCT_14M. LOGIN: TOR_EXIT_185.220.101.x. PW_CHANGE: T-2H. TRANSFER: £800 NEW_PAYEE. Pattern: ATO_CLASSIC. Rules: TOR_IP(CRITICAL), DORMANT_REACTIVATE, PW_CHANGE_PRE_TXN, NEW_PAYEE_IMMEDIATE.",
        "rs_a": "Risk Score: 99/100 (CRITICAL — Account Takeover). Factors: (1) Tor exit node login — 99.7% of Tor-based banking logins are fraudulent (industry data); (2) Password change immediately before large transfer — classic lockout-then-steal pattern; (3) Account dormant 14 months — reactivation after long dormancy is a known ATO vector; (4) New payee + immediate large transfer. This is almost certainly an account takeover. Recommendation: Immediate account freeze, force-lock all active sessions, contact customer on registered phone number.",
        "rs_b": "RISK_SCORE: 99. CRITICAL_ATO. TOR_LOGIN(+40), PW_CHANGE_PRE_TXN(+30), DORMANT_REACT(+20), NEW_PAYEE_FAST(+9). ACTION: ACCT_FREEZE_IMMEDIATE + SESSION_KILL_ALL + CUST_PHONE_CONTACT.",
        "cn_a": "URGENT: We've frozen your account for your protection. We detected unusual activity — someone logged in and changed your password before attempting a transfer, and the login came from a type of internet connection associated with fraud. Your money is safe and secure. Please call us immediately on [24h fraud number] using the phone number registered on your account. Do NOT use any links in emails you may have received — our team will never ask for your full password or PIN.",
        "cn_b": "ACCT_FREEZE_NOTICE: ATO_SUSPECTED. ALL_SESSIONS_KILLED. TXN_BLOCKED. Call [24h fraud line] immediately. DO_NOT_CLICK_LINKS. Ref: FRD-2024-CRITICAL-0012.",
        "as_a": "Immediate: (1) Freeze all account access; (2) Kill all active authenticated sessions; (3) Block the pending £800 transfer; (4) Attempt outbound call to customer's registered phone — NOT the number on the Tor session; (5) If customer confirms ATO: initiate full account takeover investigation, review all activity since dormancy ended, check for data breach correlation; (6) Require identity re-verification before restoring access; (7) Report to Action Fraud (UK) or relevant authority; (8) Flag IP range 185.220.101.x to threat intelligence team.",
        "as_b": "IMMED: FREEZE_ALL + KILL_SESSIONS + BLOCK_TXN. OUTBOUND_CALL_REG_PHONE. ATO_CONFIRMED: FULL_ATO_INVEST + ACTIVITY_REVIEW + BREACH_CORR + ID_REVERIFY. REPORT_ACTION_FRAUD. FLAG_IP_TI.",
    },
    {
        "label": "card-not-present-spike",
        "alert": "CNP fraud pattern: 8 online transactions in 24 hours totalling £2,340. All international merchants (US, Germany, Japan). Cardholder's online spend baseline: 2-3 CNP transactions/month, avg £65 each. Physical card used at UK ATM 30 minutes before CNP spike began.",
        "ta_a": "Transaction Analysis: Physical card used at UK ATM (confirming cardholder in the UK), followed 30 minutes later by 8 international CNP transactions — suggesting the card's details were cloned or intercepted, not the physical card. 8 international CNP transactions in 24 hours vs baseline of 2-3/month is a 12-16× velocity increase. The physical ATM use confirms the legitimate cardholder is in the UK, making 3-country simultaneous online spending implausible.",
        "ta_b": "CNP_SPIKE: 8 intl TXNs / 24H, £2340. Baseline: 2-3 CNP/mo, £65 avg. ATM_CP_UK: T-30min. Countries: US, DE, JP. Rules: CNP_VEL_HIGH, GEO_IMPOSSIBLE (UK_ATM + INTL_CNP), AMT_SPIKE.",
        "rs_a": "Risk Score: 96/100 (CRITICAL). Factors: (1) Geo-impossible pattern: confirmed physical presence in UK (ATM) with simultaneous international CNP transactions — mathematically impossible for legitimate cardholder; (2) 16× CNP velocity increase; (3) Card details likely compromised — e-skimming, dark web purchase, or phishing. This is near-certain card detail fraud. Recommendation: Immediate block on all further CNP transactions, leave physical card active (cardholder in UK), real-time customer notification.",
        "rs_b": "RISK_SCORE: 96. CRITICAL. GEO_IMPOSSIBLE(+40), CNP_VEL_16X(+32), CARD_COMP_LIKELY(+24). ACTION: CNP_BLOCK_IMMEDIATE + PHYS_CARD_ACTIVE + URGENT_NOTIFY.",
        "cn_a": "We've blocked online payments on your card immediately. Here's why: your card was used at a UK cash machine 30 minutes before 8 online purchases appeared from the US, Germany, and Japan — which isn't possible if you're in the UK. Your card details appear to have been stolen for online use, but the physical card in your pocket is fine. We're sending you a new card in 24 hours. In the meantime, you can still use your physical card in shops and at ATMs. Please review the 8 transactions listed below and let us know if any were yours.",
        "cn_b": "CARD_DETAIL_COMP_ALERT: CNP_BLOCKED. Phys_card active. 8 CNP_TXN_SUSPECT_LIST. Review app. New card: 24H. Ref: FRD-2024-0887.",
        "as_a": "Actions: (1) Block CNP/online channels on card, leave physical card active for UK use; (2) Initiate bulk fraud claim for all 8 CNP transactions; (3) Reissue card with new number within 24 hours; (4) Attempt chargebacks on all 8 merchants; (5) Trigger e-skimming investigation: review cardholder's recent online merchant history for compromised sites; (6) Notify customer of all 8 transactions for records; (7) Advise customer to check for phishing emails or unusual account logins on linked services.",
        "as_b": "CNP_BLOCK + PHYS_ACTIVE. BULK_FRAUD_CLAIM_8. CARD_REISSUE_24H. CB_X8. ESKIMMING_INV. CUST_NOTIFY_8_TXN. ADVIS_PHISH_CHECK.",
    },
    {
        "label": "pension-access-unusual",
        "alert": "Pension account alert: £35,000 lump sum withdrawal request submitted. Account holder age: 48. UK minimum pension access age: 55 (rising to 57 in 2028). Second withdrawal attempt in 30 days (first declined). Contact made from new device, unrecognised IP.",
        "ta_a": "Transaction Analysis: £35,000 pension withdrawal request from a 48-year-old — 7 years below UK minimum access age (55). This may indicate: (a) pension liberation fraud — fraudster targeting vulnerable individual with promises of early access; (b) account takeover targeting pension funds; (c) genuine emergency with incorrect understanding of rules. Second attempt in 30 days from new device/IP raises fraud risk. UK pension liberation fraud causes average losses of £50,000 per victim (FCA data).",
        "ta_b": "PENSION_EARLY_ACCESS: £35K withdrawal request. Account holder: 48yo (below access age 55). 2nd_attempt_30D. New_device, new_IP. Rules: AGE_BELOW_MIN(+CRITICAL), REPEAT_ATTEMPT, NEW_DEVICE_LOGIN.",
        "rs_a": "Risk Score: 94/100 (CRITICAL — Pension Liberation Fraud Indicator). Factors: (1) Below minimum access age — legally impermissible under current UK legislation (Finance Act 2004); (2) Second attempt in 30 days — persistent targeting pattern; (3) New device and IP — possible account takeover; (4) Large sum (£35,000). Regulatory note: FCA requires firms to proactively refer potential pension liberation cases to MoneyHelper and consider delaying transfer requests. Recommendation: Block transaction, mandatory welfare check call to account holder's registered number.",
        "rs_b": "RISK_SCORE: 94. CRITICAL. AGE_UNDER_MIN(+40), PENSION_LIB_PATTERN(+30), NEW_DEVICE(+15), REPEAT_ATT(+9). ACTION: BLOCK_TXN + WELFARE_CALL + FCA_CONSIDER.",
        "cn_a": "We need to speak with you urgently before processing this request. We've paused your pension withdrawal because: (1) UK law doesn't currently allow pension access before age 55; (2) This is your second request, and the new device used raises concerns for us. If someone has told you they can unlock your pension early, please be aware this is a common scam that has cost UK savers millions of pounds. We want to make sure you're protected. Please call us on [number] — we won't discuss this by email or message.",
        "cn_b": "PENSION_ACCESS_BLOCKED: Age 48 < min access age 55. 2nd_attempt. Welfare check required. Call [number] immediately. Potential pension liberation fraud. Ref: FRD-2024-0339.",
        "as_a": "Mandatory welfare check: outbound call to registered phone number only (not the new device). Call script: (1) Verify identity; (2) Explain minimum access age (55); (3) Ask who advised early access was possible; (4) Provide MoneyHelper referral and Pension Wise guidance; (5) If customer appears pressured or coerced: involve vulnerable customer team, consider delaying 30 days and re-contacting. Report to FCA if pension liberation scheme suspected. Document all interactions. Do not process request regardless of customer persistence until age criteria is met or HMRC exception confirmed.",
        "as_b": "MANDATORY_WELFARE_CALL. VERIFY_ID. EXPLAIN_MIN_AGE. MONEYHELPER_REFER. IF_COERCED: VULN_TEAM + 30D_DELAY. FCA_REPORT_IF_LIB_SCHEME. DO_NOT_PROCESS.",
    },
]


def check_backend():
    print("[check] Connecting to Forkmark backend...")
    try:
        r = httpx.get(BASE_URL + "/api/stats", timeout=5)
        r.raise_for_status()
        print(f"[check] ✓ Backend reachable at {BASE_URL}")
    except Exception:
        print(f"\n[error] Cannot reach {BASE_URL}/api/stats")
        print("  Make sure the Forkmark backend is running:")
        print("  cd forkmark && uvicorn backend.main:app --reload\n")
        sys.exit(1)

    # Auto-bootstrap an API key if none was provided via environment
    if "X-API-Key" not in HEADERS:
        print("[check] No FORKMARK_API_KEY set — bootstrapping one...")
        try:
            kr = httpx.post(
                BASE_URL + "/api/keys",
                json={"name": "demo-seeder"},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            kr.raise_for_status()
            raw_key = kr.json().get("raw_key", "")
            if raw_key:
                HEADERS["X-API-Key"] = raw_key
                print(f"[check] ✓ API key created: {raw_key[:12]}...\n")
            else:
                print("[error] Could not bootstrap API key (no raw_key in response)")
                print("  Set FORKMARK_API_KEY or create a key via the UI.")
                sys.exit(1)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("[error] API keys already exist. Provide one via FORKMARK_API_KEY env var.")
                print("  Or run via: python run_all_demos.py (which bootstraps a shared key)")
                sys.exit(1)
            raise
        except Exception as e:
            print(f"[error] Could not bootstrap API key: {e}")
            print("  Set FORKMARK_API_KEY env var or create a key manually.")
            sys.exit(1)


def seed():
    check_backend()

    print("═" * 65)
    print("  FORKMARK FINANCIAL SERVICES DEMO SEEDER")
    print("  Fraud Alert Explanation — 10 Cases × 4 Steps")
    print("═" * 65 + "\n")

    print("[1/4] Creating workflow...")
    wf = api("post", "/api/workflows", {
        "name": "fraud-alert-explanation",
        "description": "4-step fraud alert pipeline: transaction analysis, risk scoring, customer notification, and action steps.",
    })
    if not wf:
        wfs = api("get", "/api/workflows")
        wf  = next((w for w in (wfs or []) if w["name"] == "fraud-alert-explanation"), None)
    if not wf:
        print("[error] Could not create or find workflow.")
        sys.exit(1)
    print(f"       workflow id: {wf['id']}\n")

    print("[2/4] Creating eval run...")
    er = api("post", "/api/eval-runs", {
        "workflow_name": "fraud-alert-explanation",
        "name": "Plain-Language Prompt v2 vs Technical Alert v1 — Fraud Communications",
        "description": "Evaluating whether plain-language customer-facing fraud alerts reduce customer confusion and improve response rates vs technical internal alert format across 10 fraud scenario types.",
        "branch_a_config": {"label": "Plain-Language Customer Prompt v2 (Baseline)", "model_id": "gpt-4o", "temperature": 0.2},
        "branch_b_config": {"label": "Technical Internal Alert v1 (Challenger)", "model_id": "gpt-4o", "temperature": 0.2},
        "total_cases": len(CASES),
    })
    if not er:
        print("[error] Could not create eval run.")
        sys.exit(1)
    er_id = er["id"]
    print(f"       eval run id: {er_id}\n")

    print(f"[3/4] Seeding {len(CASES)} test cases (4 steps each)...")
    print()

    for i, c in enumerate(CASES):
        print(f"  [{i+1:02d}/{len(CASES)}] {c['label']}")

        run = api("post", "/api/sdk/runs", {
            "workflow_name":   "fraud-alert-explanation",
            "input_data":      {"alert": c["alert"], "label": c["label"]},
            "eval_run_id":     er_id,
            "test_case_label": c["label"],
        })
        if not run:
            print("         [skip] run creation failed")
            continue

        ba = api("post", "/api/sdk/branches", {
            "run_id": run["id"], "name": "plain-language-v2", "model_id": "gpt-4o",
            "temperature": 0.2, "is_baseline": True,
        })
        bb = api("post", "/api/sdk/branches", {
            "run_id": run["id"], "name": "technical-alert-v1", "model_id": "gpt-4o",
            "temperature": 0.2, "is_baseline": False,
        })
        if not ba or not bb:
            print("         [skip] branch creation failed")
            continue

        steps = [
            ("transaction_analysis",    c["ta_a"], c["ta_b"]),
            ("risk_scoring",            c["rs_a"], c["rs_b"]),
            ("customer_notification",   c["cn_a"], c["cn_b"]),
            ("action_steps",            c["as_a"], c["as_b"]),
        ]
        msg = [{"role": "user", "content": c["alert"]}]
        for idx, (step, out_a, out_b) in enumerate(steps):
            base_in = 70 + len(c["alert"]) // 4
            api("post", "/api/sdk/steps", {
                "run_id": run["id"], "branch_id": ba["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_a,
                "model_id": "gpt-4o", "temperature": 0.2,
                "tokens_input": base_in, "tokens_output": len(out_a.split()),
                "latency_ms": 380 + idx * 60,
            })
            api("post", "/api/sdk/steps", {
                "run_id": run["id"], "branch_id": bb["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_b,
                "model_id": "gpt-4o", "temperature": 0.2,
                "tokens_input": base_in, "tokens_output": len(out_b.split()),
                "latency_ms": 160 + idx * 28,
            })

        api("post", f"/api/sdk/runs/{run['id']}/complete", {"status": "completed"})
        comp = api("post", "/api/sdk/comparisons", {
            "run_id": run["id"],
            "branch_a_id": ba["id"],
            "branch_b_id": bb["id"],
            "eval_run_id": er_id,
            "test_case_label": c["label"],
        })
        if comp:
            d = comp.get("divergence_score", 0) or 0
            bar = "█" * int(d * 20) + "░" * (20 - int(d * 20))
            emoji = "🟢" if d < 0.2 else "🟡" if d < 0.5 else "🔴"
            print(f"         {emoji} divergence: {bar}  {d:.0%}")

    print()
    print("[4/4] Completing eval run...")
    api("patch", f"/api/eval-runs/{er_id}/complete", {
        "status": "completed", "total_cases": len(CASES),
    })

    print()
    print("═" * 65)
    print("  FINANCIAL SERVICES DEMO READY")
    print("═" * 65)
    print()
    print("  Open Forkmark:  http://localhost:5173")
    print(f"  Eval Run ID:     {er_id}")
    print()
    print("  High-divergence cases to review:")
    print("  • dormant-account-activity   — ATO pattern; plain vs technical language")
    print("  • new-payee-large-transfer   — APP fraud; Branch A has scam call script")
    print("  • pension-access-unusual     — Pension liberation; Branch A adds FCA ref")
    print("  • rapid-successive-txns      — Branch A explains fraud pattern to customer")
    print()


if __name__ == "__main__":
    seed()
