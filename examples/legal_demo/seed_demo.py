"""
Forkmark Legal Demo — Contract Clause Risk Review
===================================================

Workflow:  contract-clause-risk-review
Eval run:  GPT-4o-mini Baseline vs GPT-4o + Legal Context Prompt
Branches:
  A — GPT-4o + Legal Context Prompt (baseline — wins this eval)
  B — GPT-4o-mini Baseline          (challenger — surface-level output)

12 contract clause cases × 4 steps each:
  clause_identification · risk_classification · risk_narrative · recommended_action

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
        "label": "broad-indemnification-clause",
        "clause": "The Vendor shall indemnify, defend, and hold harmless the Client, its officers, directors, employees, and agents from any and all claims, damages, losses, costs, and expenses (including reasonable legal fees) arising out of or relating to the Vendor's performance under this Agreement, whether or not caused by the negligence of the Client.",
        # clause_identification
        "ci_a": "Clause type: Indemnification (broad / mutual-style drafted one-sidedly). Scope: all claims arising from Vendor performance, including Client negligence. Party obligated: Vendor only. Notable: 'whether or not caused by the negligence of the Client' — uncapped, unilateral indemnity.",
        "ci_b": "This is an indemnification clause requiring the vendor to cover the client's losses.",
        # risk_classification
        "rc_a": "SEVERITY: HIGH. Risk type: Unlimited financial exposure. The phrase 'whether or not caused by the negligence of the Client' transfers risk of Client's own negligence to Vendor — courts in many jurisdictions require express language to achieve this but it is present here. No indemnity cap or basket. No carve-out for Client's gross negligence or wilful misconduct.",
        "rc_b": "High risk. Vendor pays for everything including client's own mistakes.",
        # risk_narrative
        "rn_a": "This clause creates uncapped, unilateral indemnification including scenarios caused by the Client's own negligence. Key problems: (1) No monetary cap — exposure is unlimited; (2) No exclusion for Client gross negligence or wilful misconduct; (3) Defence obligation adds litigation cost burden even for frivolous claims; (4) 'Arising out of or relating to' is expansively drafted — courts typically read this broadly. In practice, this could make the Vendor liable for losses entirely outside its control. Standard market practice: mutual indemnification, capped at contract value, with gross negligence / fraud carve-outs.",
        "rn_b": "The vendor would have to pay even if the client caused the problem. This is unusual and could be very expensive.",
        # recommended_action
        "ra_a": "1. INSERT monetary cap: 'Vendor's total indemnification liability shall not exceed the aggregate fees paid in the preceding 12 months.' 2. DELETE 'whether or not caused by the negligence of the Client' — replace with 'to the extent caused by Vendor's acts or omissions.' 3. ADD mutual indemnification: Client to indemnify Vendor for claims arising from Client's own negligence. 4. ADD exclusion: 'Notwithstanding the foregoing, Vendor shall have no obligation to indemnify for losses arising from Client's gross negligence or wilful misconduct.' 5. REQUIRE Client to provide prompt written notice and grant Vendor control of defence.",
        "ra_b": "Negotiate to limit the indemnity to vendor's own fault and add a financial cap. Remove the client negligence language.",
    },
    {
        "label": "ip-assignment-work-for-hire",
        "clause": "All work product, inventions, discoveries, developments, improvements, and intellectual property created by the Vendor in connection with the Services, whether or not patentable or copyrightable, shall be the sole and exclusive property of the Client. Vendor hereby assigns all right, title, and interest therein to Client.",
        "ci_a": "Clause type: IP Assignment / Work-for-Hire. Scope: all work product and IP created 'in connection with' the Services. Assignment: present-tense ('hereby assigns') — self-executing. Coverage: inventions, discoveries, developments, improvements — broad catch-all.",
        "ci_b": "The client owns everything the vendor creates. Vendor gives up all IP rights.",
        "rc_a": "SEVERITY: HIGH (for Vendor). Risk type: Overbroad IP assignment. 'In connection with' is significantly broader than 'pursuant to' or 'specifically for' — could capture pre-existing IP inadvertently used in delivery, or Vendor's general-purpose tools/frameworks. No carve-out for Vendor's background IP or pre-existing materials. If Vendor is a software developer, this could transfer ownership of reusable code libraries.",
        "rc_b": "High risk for vendor. They could lose IP they had before this contract.",
        "rn_a": "The clause uses 'in connection with' rather than 'specifically created for' — this distinction is critical. Vendor risks assigning: (1) pre-existing IP incorporated into deliverables; (2) general tools or frameworks developed independently but used in performance; (3) innovations conceived during the engagement but unrelated to the specific brief. The present-tense assignment ('hereby assigns') is self-executing and requires no further instrument. There is no licence-back to Vendor for its own background IP.",
        "rn_b": "Vendor might accidentally assign IP they already owned. The language is too broad.",
        "ra_a": "1. LIMIT scope: replace 'in connection with the Services' with 'specifically and exclusively created for Client under this Agreement.' 2. ADD Background IP carve-out: 'Client acknowledges that Vendor retains all right, title and interest in Vendor's Background IP (pre-existing materials, tools, and frameworks). Client receives a non-exclusive licence to use Background IP solely to the extent embedded in deliverables.' 3. ADD Vendor tools exclusion: standard reusable code libraries and development tools remain Vendor property. 4. CONSIDER revenue share or joint ownership for jointly developed innovations.",
        "ra_b": "Add a carve-out for vendor's pre-existing IP. Limit the assignment to work specifically made for the client.",
    },
    {
        "label": "non-compete-two-year",
        "clause": "During the term of this Agreement and for a period of two (2) years following termination, the Vendor shall not, directly or indirectly, engage in, invest in, or provide services to any business that competes with the Client's business in any jurisdiction in which the Client operates.",
        "ci_a": "Clause type: Non-Compete Restriction. Duration: 2 years post-termination. Geographic scope: all jurisdictions where Client operates (undefined — potentially global). Activity scope: broad — 'engage in, invest in, provide services to' any competing business. Party bound: Vendor.",
        "ci_b": "Vendor cannot work for competitors for 2 years anywhere the client does business.",
        "rc_a": "SEVERITY: HIGH. Risk type: Unenforceable / overbroad restraint of trade. Issues: (1) 2-year duration is at the upper bound of enforceability in most common law jurisdictions; courts scrutinise non-competes strictly; (2) 'Any jurisdiction where Client operates' — if Client is multinational, this is a de facto global restriction; (3) No geographic limitation makes enforceability unlikely in UK (post-Tillman v Egon Zehnder), EU, and many US states; (4) 'Invest in' could restrict passive shareholdings; (5) Client's business is undefined — scope uncertainty.",
        "rc_b": "Probably too broad to enforce. 2 years globally is a lot.",
        "rn_a": "Courts in the UK, EU, and most US states apply a reasonableness test to non-compete clauses. This clause fails multiple criteria: the geographic scope (any jurisdiction Client operates) is likely global given no definition of 'Client's business areas'; the 2-year duration, combined with global reach, is disproportionate for a service vendor relationship (as distinct from a senior employee). The investment restriction could prevent Vendor from holding minor shareholdings in publicly listed companies in adjacent sectors. UK courts may blue-pencil, but EU competition law (Art. 101 TFEU) and many US state laws (California, Minnesota, North Dakota) render such clauses void. Enforceability depends heavily on jurisdiction of governing law.",
        "rn_b": "This restriction is probably too broad and might not hold up in court. Should be narrowed.",
        "ra_a": "1. REDUCE duration: 12 months is standard for vendor relationships; 6 months if Vendor is an individual contractor. 2. DEFINE geographic scope: limit to specific named territories where Vendor actually performed services. 3. DEFINE 'competing business': narrow to specific product/service lines, not entire industry. 4. REMOVE 'invest in' — replace with 'invest in excess of 5% equity in.' 5. ADD consideration: courts are more likely to enforce non-competes supported by specific payment (non-compete fee). 6. REVIEW governing law — if agreement is governed by California law, non-compete is void ab initio.",
        "ra_b": "Narrow the geography, reduce the time period, and define what counts as a competitor. Consider adding payment for the restriction.",
    },
    {
        "label": "auto-renewal-evergreen",
        "clause": "This Agreement shall automatically renew for successive one-year terms unless either party provides written notice of non-renewal at least ninety (90) days prior to the end of the then-current term. Fees shall increase by 8% upon each renewal.",
        "ci_a": "Clause type: Auto-Renewal (Evergreen) with Price Escalation. Renewal: automatic annual, unless 90-day notice given. Fee escalation: 8% per renewal cycle (compounding). Notice requirement: 90 days — longer than market standard (30-60 days). Risk party: Client (paying party locked into 8% annual increases).",
        "ci_b": "Contract auto-renews every year with an 8% price increase. Need 90 days' notice to cancel.",
        "rc_a": "SEVERITY: MEDIUM-HIGH. Risk type: Contractual lock-in and compounding cost escalation. Issues: (1) 8% annual increase significantly exceeds UK CPI (currently ~2.5%) and US CPI — over 3 years represents ~26% cumulative cost increase; (2) 90-day notice window is unusually long — if missed, Client is locked in for another year plus the 8% increase; (3) No cap on escalation over contract lifetime; (4) In B2C contexts, auto-renewal with price increase may trigger CMA / FTC consumer protection obligations (transparency required).",
        "rc_b": "8% price increase every year will add up. 90-day notice is a long time to remember.",
        "rn_a": "The combination of auto-renewal and 8% annual fee escalation creates significant long-term cost exposure. At 8% compounding: year 2 fees = 108% of year 1; year 5 fees = ~147% of year 1. This exceeds typical CPI-linked escalation (which would be 2-4% in most Western markets). The 90-day notice window creates an operational risk — procurement and legal teams need calendar reminders well in advance of the deadline. If notice is missed, Client is locked in for another 12 months at the escalated rate. For multi-year engagements, this clause can materially distort original contract economics.",
        "rn_b": "Costs will rise significantly over time. Easy to miss the 90-day window and get locked in.",
        "ra_a": "1. LINK escalation to index: replace fixed 8% with 'lesser of 5% or UK CPI/US CPI + 2%.' 2. REDUCE notice period: 30-60 days is market standard; 90 days creates operational risk. 3. ADD termination for convenience: right to terminate on 30 days' notice at any renewal point without cause. 4. ADD escalation cap: 'Notwithstanding the foregoing, cumulative fee increases shall not exceed 25% of the original contract value over the Initial Term.' 5. ADD notification obligation: Vendor to send written reminder of upcoming renewal and new fee schedule at least 120 days before notice deadline.",
        "ra_b": "Link the price increase to inflation, shorten the notice period, and add a way to exit the contract.",
    },
    {
        "label": "limitation-of-liability",
        "clause": "In no event shall either party be liable to the other for any indirect, incidental, special, or consequential damages, including but not limited to loss of profits or revenue, regardless of the cause of action or whether such party has been advised of the possibility of such damages. Each party's total liability shall not exceed the total fees paid in the three months preceding the claim.",
        "ci_a": "Clause type: Mutual Limitation of Liability (LOL). Exclusions: indirect, incidental, special, consequential damages; loss of profits/revenue. Cap: fees paid in preceding 3 months (rolling). Applicability: mutual. Notable: 3-month cap may be very low for long-standing or high-value engagements.",
        "ci_b": "Neither party can claim for lost profits. Liability is capped at 3 months of fees.",
        "rc_a": "SEVERITY: MEDIUM (mutual, but asymmetric in practice). Risk type: Inadequate compensation cap and exclusion of core losses. Issues: (1) 3-month rolling cap is low — for a £500K/year contract, cap = £125K, potentially insufficient for material breaches; (2) Loss of profits exclusion protects both parties but may leave Client uncompensated for a critical system failure that caused revenue loss; (3) Cap may be challengeable for: fraud, wilful misconduct, death/personal injury (UK Unfair Contract Terms Act 1977, s2); (4) Consequential damages exclusion may be unenforceable in some US states for consumer contracts.",
        "rc_b": "The cap might be too low and could leave you undercompensated for a big failure.",
        "rn_a": "The 3-month rolling cap is the most commercially significant risk. For a £1M/year engagement, this limits total recovery to ~£250K regardless of the severity of breach. Standard market practice for technology and professional services contracts is to cap at 12 months' fees or the total contract value. The consequential damages exclusion, while mutual, disproportionately affects the Client in the event of a service failure causing downstream business loss (e.g., SaaS outage causing lost sales). UK courts have struck down LOL clauses that fail the reasonableness test under UCTA 1977 in B2B contexts. Carve-outs for death/personal injury, fraud, and wilful misconduct are legally required under UK law.",
        "rn_b": "The cap is quite low and loss of profits exclusion could hurt the client more than the vendor.",
        "ra_a": "1. INCREASE cap: negotiate to 12 months' fees or total contract value — whichever is greater. 2. ADD mandatory carve-outs (legally required in UK): death/personal injury; fraud; wilful misconduct. 3. CONSIDER separate cap for data breach: 150-200% of annual fees (aligns with ICO fine risk). 4. ADD specific exclusion: 'This clause shall not limit either party's obligation to pay undisputed invoices.' 5. REVIEW consequential damages exclusion for critical services — negotiate carve-out for 'direct loss of Client data.'",
        "ra_b": "Increase the cap to 12 months of fees. Add carve-outs for fraud and personal injury as legally required.",
    },
    {
        "label": "governing-law-dispute-resolution",
        "clause": "This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware, without regard to its conflict of laws provisions. Any dispute shall be resolved exclusively by binding arbitration administered by the AAA under its Commercial Arbitration Rules in New York, New York.",
        "ci_a": "Clause type: Governing Law + Dispute Resolution (Arbitration). Governing law: Delaware (US). Forum: AAA arbitration, New York. Binding: yes. Note: mandatory arbitration waives right to jury trial and class action; New York venue imposes travel cost on non-US parties.",
        "ci_b": "Delaware law applies. All disputes go to arbitration in New York.",
        "rc_a": "SEVERITY: MEDIUM. Risk type: Jurisdictional mismatch and arbitration cost asymmetry. Issues: (1) If the counterparty is non-US, mandatory New York arbitration imposes significant travel and legal costs; (2) AAA Commercial Rules filing fees are substantial ($2,000–$10,000+ depending on claim value); (3) Delaware law may differ significantly from the party's home jurisdiction on key issues (employment, IP, consumer rights); (4) Mandatory arbitration waives right to appeal on merits — no review of legal errors; (5) For UK/EU parties, Brussels Regulation and Lugano Convention may create enforceability issues.",
        "rc_b": "Could be expensive and inconvenient for non-US companies. Arbitration limits appeal rights.",
        "rn_a": "For a non-US contracting party, this clause has three significant practical impacts: (1) All disputes must be resolved in New York under AAA rules — international travel costs and time zone coordination for hearings; (2) AAA fees alone for a $500K dispute can exceed $15,000 before legal fees; (3) Delaware law governs substantive issues — the party's local counsel may not be admitted in Delaware. The 'without regard to conflict of laws' provision locks in Delaware law even where another jurisdiction would apply under standard conflict of laws analysis. For UK parties post-Brexit, enforcement of US arbitral awards requires recognition under the New York Convention — generally available but adds process.",
        "rn_b": "Non-US parties will face high costs. Arbitration is expensive and limits court challenges.",
        "ra_a": "1. NEGOTIATE governing law to neutral jurisdiction or home jurisdiction of both parties (e.g., England and Wales for UK-US deals — respected internationally). 2. ADD tiered dispute resolution: (a) escalation to senior management (30 days); (b) mediation (CEDR/AAA); (c) arbitration only as last resort. 3. NEGOTIATE venue: consider ICC Paris or LCIA London for international deals — lower costs, internationally recognised. 4. ADD small claims carve-out: disputes under $25K may be resolved in local courts to avoid disproportionate arbitration costs. 5. ADD class action rights preservation for consumer-facing businesses.",
        "ra_b": "Consider a neutral governing law and a cheaper dispute resolution process. Add mediation before arbitration.",
    },
    {
        "label": "termination-for-convenience",
        "clause": "Either party may terminate this Agreement for convenience upon thirty (30) days' written notice. Upon termination, the Client shall pay all fees accrued through the termination date. Vendor shall have no further obligations to Client following the effective date of termination.",
        "ci_a": "Clause type: Termination for Convenience (mutual). Notice: 30 days. Client obligation on termination: accrued fees only. Vendor obligation on termination: none. Notable gaps: no transition assistance obligation; no data return/deletion; no wind-down services.",
        "ci_b": "Either side can cancel with 30 days' notice. Client pays what they owe up to that date.",
        "rc_a": "SEVERITY: MEDIUM. Risk type: Operational continuity gap on exit. Issues: (1) 30 days may be insufficient for Client to transition to a new vendor (especially for technology services); (2) No transition services obligation — Vendor can simply stop on day 30, leaving Client without operational support; (3) No data portability obligation — Vendor has no obligation to return or delete Client data; (4) No handover documentation obligation; (5) For SaaS/cloud services, 30-day wind-down may be inadequate to export data and migrate systems.",
        "rc_b": "Vendor doesn't have to help with transition. Could leave client stranded without data.",
        "rn_a": "This clause is adequate for simple service engagements but creates material risk for technology, data processing, or mission-critical service contracts. On the effective date, Vendor has zero obligation to assist with transition — they can shut down access, delete data, or cease support immediately. For a SaaS platform with complex integrations, 30 days is typically insufficient to: (1) export all data in usable formats; (2) procure and onboard a replacement vendor; (3) retrain staff on a new system. The clause also creates GDPR/DPA 2018 risk — no explicit obligation to return or certifiably delete personal data on termination violates Art. 28(3)(g) GDPR processor requirements for any personal data processed.",
        "rn_b": "Vendor has no transition obligations. For tech services this is a serious gap, especially for data return.",
        "ra_a": "1. ADD Transition Services clause: 'Upon notice of termination, Vendor shall provide up to 90 days of transition assistance at current rates, including data export, documentation, and handover support.' 2. EXTEND effective notice for complex services: 90 days for technology/SaaS contracts. 3. ADD Data Return obligation: 'Within 30 days of termination, Vendor shall provide all Client data in machine-readable format and certifiably delete all copies per Client's instructions.' (Required by GDPR Art. 28.) 4. ADD Surviving obligations: list clauses that survive termination (IP, confidentiality, payment). 5. ADD Step-in rights: Client right to hire key Vendor personnel during transition for continuity.",
        "ra_b": "Add a transition services obligation. Make sure data return is required. Consider longer notice for tech contracts.",
    },
    {
        "label": "data-processing-agreement",
        "clause": "Vendor may process Client's data solely for the purposes of providing the Services. Vendor shall implement reasonable security measures to protect such data. Vendor shall notify Client of any data breach within a reasonable time.",
        "ci_a": "Clause type: Data Processing Agreement (DPA) — inadequate. Scope: purpose limitation present but weak. Security: 'reasonable measures' — undefined standard. Breach notification: 'reasonable time' — non-compliant with GDPR (72h mandatory). Critical gaps: no sub-processor list, no DPA art. 28 mandatory terms, no data subject rights obligations.",
        "ci_b": "Vendor will protect the data and tell you about breaches. Vague on details.",
        "rc_a": "SEVERITY: CRITICAL. Risk type: GDPR non-compliance — regulatory and contractual. Issues: (1) 'Reasonable time' breach notification violates GDPR Art. 33 (72-hour notification to supervisory authority mandatory); (2) No sub-processor authorisation mechanism — GDPR Art. 28(2) requires Client consent for sub-processors; (3) No data subject rights obligations on Vendor — Art. 28(3)(e) requires Vendor to assist with DSARs; (4) 'Reasonable security measures' is insufficient — GDPR requires 'appropriate technical and organisational measures' per Art. 32 risk assessment; (5) No data transfer provisions — if Vendor uses international sub-processors, SCCs or equivalent required.",
        "rc_b": "This DPA is not GDPR compliant. '72 hours' is missing. Sub-processors not covered.",
        "rn_a": "This clause fundamentally fails to meet GDPR Article 28 requirements for a lawful Data Processing Agreement. The ICO and EU DPAs have issued significant fines for inadequate DPAs — the fact that a contract contains a DPA clause does not provide compliance cover if it omits mandatory terms. Key failures: 'reasonable time' breach notification creates direct GDPR Art. 33 violation exposure (up to 4% global annual turnover); absence of sub-processor controls means Client has no visibility into who is processing its data; no data deletion/return obligation at termination means data may be retained indefinitely in violation of Art. 5(1)(e) storage limitation. This clause must be replaced with a compliant DPA, not merely amended.",
        "rn_b": "This clause will cause GDPR compliance failures. Replace it entirely with a proper DPA.",
        "ra_a": "REPLACE entirely with a GDPR-compliant DPA containing all Art. 28(3) mandatory terms: (a) process only on documented Client instructions; (b) confidentiality obligations on Vendor personnel; (c) implement Art. 32 appropriate technical/organisational security measures; (d) sub-processor authorisation process with Client approval; (e) assist with data subject rights requests; (f) assist with security, breach notification, DPIA; (g) delete or return all data on termination; (h) provide audit rights. SPECIFY: 72-hour breach notification (Art. 33); list of authorised sub-processors as an Annex; SCCs for any international transfers. Consider using the ICO's standard DPA template as a baseline.",
        "ra_b": "Replace this clause entirely. Use a full GDPR-compliant DPA with 72-hour breach notification and sub-processor controls.",
    },
    {
        "label": "penalty-clause-liquidated-damages",
        "clause": "If the Vendor fails to meet any agreed Service Level Agreement (SLA), the Vendor shall pay the Client a penalty of 10% of the monthly contract value for each day of non-compliance, up to a maximum of 100% of the total contract value.",
        "ci_a": "Clause type: Liquidated Damages / SLA Penalty. Rate: 10% of monthly contract value per day of SLA breach. Cap: 100% of total contract value. Notable: 10%/day compounding = full contract value in 10 days — likely a penalty clause (unenforceable) rather than genuine pre-estimate of loss.",
        "ci_b": "Vendor pays 10% per day for SLA breaches up to the full contract value. Very steep.",
        "rc_a": "SEVERITY: HIGH. Risk type: Unenforceable penalty clause / reverse risk (for Client seeking to enforce). Issues: (1) UK law: penalty clause test (Cavendish Square v Makdessi [2015]) — clause is enforceable only if it protects a legitimate interest and is not 'extravagant and unconscionable'; 10%/day reaching 100% in 10 days almost certainly fails this test; (2) US law: similarly, LDs must be a 'reasonable pre-estimate of loss' — 10%/day is disproportionate; (3) Clause creates adversarial relationship — Vendor incentivised to contest every SLA measurement; (4) No definition of what constitutes an SLA breach or measurement methodology.",
        "rc_b": "10% per day is probably too high to enforce in court. Needs to look like real loss estimation.",
        "rn_a": "Under Cavendish Square v Makdessi [2015] UKSC 67, English courts will enforce LDs only if they represent a proportionate means of protecting a legitimate business interest. A 10%/day penalty reaching the full contract value in 10 days is almost certainly characterised as a penalty (not genuine LDs) and will be unenforceable. Paradoxically, this harms the Client — if the clause is struck out as a penalty, Client is left with only actual proven damages (which are harder to quantify). Additionally, 'SLA' is not defined — disputes about measurement methodology are inevitable. US courts apply similar 'reasonable pre-estimate' tests — California, New York, and Texas courts have voided similarly aggressive daily penalty clauses.",
        "rn_b": "The 10%/day rate is likely to be ruled an unenforceable penalty. That actually hurts the client.",
        "ra_a": "1. REPLACE with service credits (not penalties): service credits expressed as % of monthly fee per SLA tier (e.g., 99.9% uptime target; 1-3% credit per breach tier). 2. CALIBRATE to actual loss: analyse what downstream business impact each SLA failure causes and base credits on that. 3. ADD SLA measurement methodology: define measurement window, reporting mechanism, and disputed measurement process. 4. ADD exclusions: force majeure, Client-caused outages, scheduled maintenance. 5. CONSIDER remedy-first approach: cure period before credits accrue (e.g., 4h cure for P1 issues). 6. RETAIN termination right for persistent SLA failure (e.g., 3 critical breaches in 12 months) as primary remedy.",
        "ra_b": "Replace with service credits at a reasonable level. Add SLA definitions and a cure period before penalties apply.",
    },
    {
        "label": "force-majeure-broad",
        "clause": "Neither party shall be liable for any failure or delay in performance under this Agreement to the extent such failure or delay is caused by circumstances beyond the party's reasonable control, including but not limited to acts of God, war, terrorism, epidemic, pandemic, government action, labour disputes, or internet or telecommunications failures.",
        "ci_a": "Clause type: Force Majeure. Coverage: broad — includes pandemic, epidemic, government action, internet/telecom failure. Effect: excuses performance (liability and delay). Duration: undefined — no limit on how long FM can be claimed. No termination right on extended FM.",
        "ci_b": "Standard force majeure covering pandemics and internet failures. No time limit on how long it can last.",
        "rc_a": "SEVERITY: MEDIUM. Risk type: Indefinite performance suspension without relief or exit. Issues: (1) 'Internet or telecommunications failures' — overly broad; routine ISP outages or cloud provider incidents could trigger this; (2) 'Government action' — very broad; could cover regulatory changes that merely make performance more expensive; (3) No duration limit — Vendor could claim FM indefinitely without giving Client right to terminate; (4) No mitigation obligation specified; (5) Post-COVID, 'pandemic/epidemic' is a well-known risk — courts may hold this was foreseeable and thus not a true FM event in future contracts.",
        "rc_b": "Internet failures and government action are too broad. No time limit is a problem.",
        "rn_a": "Post-COVID contracting has changed FM interpretation significantly. Courts in England and the US have generally held that pandemic disruption is now a foreseeable commercial risk — parties can no longer claim FM for pandemic events without specific contractual language. Conversely, the explicit inclusion of 'pandemic' here does provide FM cover, which benefits the party seeking to rely on it. The most significant gaps are: (1) no mitigation obligation — party claiming FM should be required to take reasonable steps to overcome the impediment; (2) no maximum duration — FM could theoretically continue indefinitely, leaving the other party in limbo; (3) 'internet or telecommunications failures' is drafted so broadly it could cover routine service degradation rather than genuine extraordinary events.",
        "rn_b": "Post-pandemic, courts may not accept pandemic as a true force majeure. The internet failure language is too vague.",
        "ra_a": "1. ADD mitigation obligation: 'The affected party shall use commercially reasonable efforts to overcome or work around the force majeure event and resume performance as soon as practicable.' 2. ADD duration cap and termination right: 'If a force majeure event continues for more than 60 days, either party may terminate this Agreement on 14 days' written notice without liability.' 3. NARROW internet/telecom: replace with 'widespread internet infrastructure failures affecting the affected party's primary service region.' 4. ADD notification obligation: 'The affected party shall provide written notice within 5 business days of the force majeure event, including estimated duration and steps being taken.' 5. CONSIDER financial hardship clause separately — distinct from traditional FM.",
        "ra_b": "Add a 60-day cap with a termination right. Narrow the internet failure language. Require mitigation.",
    },
    {
        "label": "exclusivity-restriction",
        "clause": "During the term of this Agreement, the Client agrees not to engage, directly or indirectly, any third party to provide services substantially similar to the Services provided by Vendor under this Agreement.",
        "ci_a": "Clause type: Exclusivity Restriction (Client-side). Scope: Client cannot engage any third party for 'substantially similar' services. Duration: for the term (undefined end date in this clause). 'Substantially similar' is undefined — creates uncertainty. Effect: Client cannot dual-vendor or run competitive tenders during the term.",
        "ci_b": "Client cannot use any other vendor for similar services during the contract.",
        "rc_a": "SEVERITY: MEDIUM-HIGH (for Client). Risk type: Operational lock-in and competition law risk. Issues: (1) No definition of 'substantially similar' — creates dispute risk; Vendor could argue any overlapping service triggers exclusivity; (2) Removes Client's ability to run a competitive tender or dual-vendor for resilience; (3) UK/EU competition law: exclusivity clauses in vertical agreements may violate Chapter I CA98 / Art. 101 TFEU if Vendor has market power (>30% market share triggers block exemption analysis under VABE); (4) No carve-out for services Vendor is unable or unwilling to provide; (5) No volume commitment by Vendor in exchange for exclusivity.",
        "rc_b": "Client loses flexibility and this might breach competition law if the vendor is dominant.",
        "rn_a": "Exclusivity clauses in commercial contracts are subject to competition law scrutiny in the UK (Competition Act 1998) and EU (Art. 101 TFEU). Under the Vertical Agreements Block Exemption (Regulation 2022/720), exclusivity is permissible where neither party's market share exceeds 30%, but above that threshold, individual exemption analysis is required. From a commercial perspective, Client is giving up significant value — no competitive tension during the term means no pricing pressure, no ability to run tenders, and no resilience through dual-vendor strategies. The absence of a reciprocal commitment by Vendor (guaranteed capacity, SLA, or volume discount) makes this an asymmetric bargain.",
        "rn_b": "Exclusivity without anything in return is a bad deal for the client. Competition law issues possible.",
        "ra_a": "1. DELETE or narrow scope: limit to specific service categories explicitly listed, not 'substantially similar' catch-all. 2. ADD Vendor reciprocal commitment: in exchange for exclusivity, Vendor commits to guaranteed capacity, priority SLA, and volume discount. 3. ADD carve-out: 'Exclusivity shall not apply where Vendor is unable or unwilling to provide the relevant services within [30] days of written request.' 4. ADD competition law savings clause: 'This clause shall not apply to the extent it would violate applicable competition law.' 5. CONSIDER time-limiting exclusivity: apply only to first 12 months as relationship is established.",
        "ra_b": "Narrow the scope, get something back from the vendor, and add a carve-out for services the vendor can't provide.",
    },
    {
        "label": "payment-terms-late-fees",
        "clause": "Invoices are due and payable within thirty (30) days of the invoice date. Late payments shall accrue interest at the rate of 2% per month on the outstanding balance. The Client shall reimburse Vendor for all costs of collection, including reasonable legal fees.",
        "ci_a": "Clause type: Payment Terms + Late Payment Interest. Due date: 30 days from invoice. Late interest: 2%/month (compounding = 26.8% APR effective rate). Collection costs: Client bears Vendor's legal fees. Notable: 2%/month exceeds UK Late Payment of Commercial Debts Act 1998 (8% over Bank Rate p.a.) and may be challengeable.",
        "ci_b": "30 days to pay. 2% interest per month if late. Client pays collection costs.",
        "rc_a": "SEVERITY: MEDIUM. Risk type: Excessive late payment interest and one-sided cost recovery. Issues: (1) 2%/month = 26.8% effective APR — significantly exceeds UK LPCD 1998 statutory rate (currently ~8.5% p.a.) and may be unenforceable as a penalty under English law; (2) 'All costs of collection including legal fees' is one-sided — no equivalent right for Client; (3) No dispute resolution mechanism for invoices — late interest accrues even on genuinely disputed amounts; (4) No cure period before interest accrues; (5) In US, some states cap late payment interest (e.g., California at 10% p.a. for commercial contracts).",
        "rc_b": "2% per month is very high and might not be enforceable. No protection for disputed invoices.",
        "rn_a": "Under the UK Late Payment of Commercial Debts (Interest) Act 1998, the statutory interest rate is 8% over the Bank of England base rate (currently ~8.5% p.a.). A contractual rate of 2%/month (26.8% APR) is permissible if it represents a 'substantial remedy' for late payment, but courts may still apply the LPCD Act rate as a floor rather than a ceiling. The collection costs clause creates a one-way fee-shifting mechanism — Client pays Vendor's legal fees even for partially disputed invoices. This creates a chilling effect on legitimate invoice disputes. No dispute resolution mechanism means a Client querying an incorrect invoice could be charged late interest and legal fees for the entire disputed amount while the dispute is unresolved.",
        "rn_b": "High interest rate and one-sided cost recovery. Client needs protection for disputed invoices.",
        "ra_a": "1. REDUCE interest rate: 1%/month or statutory rate under LPCD 1998 (whichever is higher) — commercially reasonable and enforceable. 2. ADD dispute carve-out: 'Late payment interest shall not accrue on amounts subject to a bona fide written dispute raised within [10] days of invoice receipt.' 3. ADD invoice dispute resolution: 'Disputed invoices shall be escalated to senior management within 5 days; undisputed portion to be paid by due date.' 4. MAKE cost recovery mutual: 'Each party shall bear its own costs unless a court awards costs.' 5. ADD cure period: 5-business-day grace period before interest begins to accrue.",
        "ra_b": "Lower the interest rate to statutory levels. Add a dispute process so interest doesn't accrue on contested amounts.",
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
    print("  FORKMARK LEGAL DEMO SEEDER")
    print("  Contract Clause Risk Review — 12 Cases × 4 Steps")
    print("═" * 65 + "\n")

    print("[1/4] Creating workflow...")
    wf = api("post", "/api/workflows", {
        "name": "contract-clause-risk-review",
        "description": "4-step contract review pipeline: clause identification, risk classification, risk narrative, and recommended action.",
    })
    if not wf:
        wfs = api("get", "/api/workflows")
        wf  = next((w for w in (wfs or []) if w["name"] == "contract-clause-risk-review"), None)
    if not wf:
        print("[error] Could not create or find workflow.")
        sys.exit(1)
    print(f"       workflow id: {wf['id']}\n")

    print("[2/4] Creating eval run...")
    er = api("post", "/api/eval-runs", {
        "workflow_name": "contract-clause-risk-review",
        "name": "GPT-4o Legal Context Prompt vs GPT-4o-mini Baseline — Contract Risk",
        "description": "Evaluating whether a GPT-4o model with legal context prompt provides materially better clause risk analysis than a GPT-4o-mini baseline across 12 common commercial contract clauses.",
        "branch_a_config": {"label": "GPT-4o + Legal Context Prompt (Baseline)", "model_id": "gpt-4o", "temperature": 0.1},
        "branch_b_config": {"label": "GPT-4o-mini Baseline (Challenger)", "model_id": "gpt-4o-mini", "temperature": 0.1},
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
            "workflow_name":   "contract-clause-risk-review",
            "input_data":      {"clause_text": c["clause"], "label": c["label"]},
            "eval_run_id":     er_id,
            "test_case_label": c["label"],
        })
        if not run:
            print("         [skip] run creation failed")
            continue

        ba = api("post", "/api/sdk/branches", {
            "run_id": run["id"], "name": "gpt-4o-legal-context", "model_id": "gpt-4o",
            "temperature": 0.1, "is_baseline": True,
        })
        bb = api("post", "/api/sdk/branches", {
            "run_id": run["id"], "name": "gpt-4o-mini-baseline", "model_id": "gpt-4o-mini",
            "temperature": 0.1, "is_baseline": False,
        })
        if not ba or not bb:
            print("         [skip] branch creation failed")
            continue

        steps = [
            ("clause_identification", c["ci_a"], c["ci_b"]),
            ("risk_classification",   c["rc_a"], c["rc_b"]),
            ("risk_narrative",        c["rn_a"], c["rn_b"]),
            ("recommended_action",    c["ra_a"], c["ra_b"]),
        ]
        msg = [{"role": "user", "content": c["clause"]}]
        for idx, (step, out_a, out_b) in enumerate(steps):
            base_in = 80 + len(c["clause"]) // 4
            api("post", "/api/sdk/steps", {
                "run_id": run["id"], "branch_id": ba["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_a,
                "model_id": "gpt-4o", "temperature": 0.1,
                "tokens_input": base_in, "tokens_output": len(out_a.split()),
                "latency_ms": 420 + idx * 70,
            })
            api("post", "/api/sdk/steps", {
                "run_id": run["id"], "branch_id": bb["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_b,
                "model_id": "gpt-4o-mini", "temperature": 0.1,
                "tokens_input": base_in, "tokens_output": len(out_b.split()),
                "latency_ms": 190 + idx * 35,
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
    print("  LEGAL DEMO READY")
    print("═" * 65)
    print()
    print("  Open Forkmark:  http://localhost:5173")
    print(f"  Eval Run ID:     {er_id}")
    print()
    print("  High-divergence cases to review:")
    print("  • data-processing-agreement — CRITICAL: GDPR non-compliance flags")
    print("  • broad-indemnification     — GPT-4o cites Cavendish Square case law")
    print("  • non-compete-two-year      — GPT-4o cites Tillman v Egon Zehnder")
    print("  • penalty-clause            — GPT-4o identifies unenforceability risk")
    print()


if __name__ == "__main__":
    seed()
