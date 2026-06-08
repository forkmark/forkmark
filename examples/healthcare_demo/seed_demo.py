"""
Forkmark Healthcare Demo — Clinical Note Summarization
=======================================================

Workflow:  clinical-note-summarization
Eval run:  Terse Prompt v1 vs Structured SOAP Prompt v2
Branches:
  A — Structured SOAP Prompt v2  (baseline — wins this eval)
  B — Terse Summary Prompt v1    (challenger — underperforms)

12 clinical cases × 4 steps each:
  symptom_extraction · diagnosis_coding · treatment_plan · discharge_summary

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
            print("  Make sure Forkmark is running (run `python run.py` first)\n")
            sys.exit(1)
        except Exception as e:
            print(f"[error] {method.upper()} {path}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  Response: {e.response.text[:200]}")
            return None
    print(f"[error] {method.upper()} {path}: rate limit retries exhausted")
    return None


def divergence(a, b):
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    j  = 1 - len(wa & wb) / (len(wa | wb) or 1)
    s  = 1 - SequenceMatcher(None, a, b).ratio()
    return round(j * 0.6 + s * 0.4, 4)


CASES = [
    {
        "label": "chest-pain-rule-out-acs",
        "patient": "62M presenting with 3h chest pain, diaphoresis, mild dyspnoea. BP 148/92, HR 96. ECG: ST depression V4-V6. Troponin pending.",
        # symptom_extraction
        "sx_a": "Symptoms: chest pain (3h), diaphoresis, dyspnoea. Vitals: BP 148/92, HR 96. ECG: ST depression V4-V6. Troponin: pending.",
        "sx_b": "Chest pain, sweating, shortness of breath.",
        # diagnosis_coding
        "dx_a": "Primary: R07.9 – Chest pain, unspecified (pending ACS rule-out). Differential: I21.9 NSTEMI, I20.9 Unstable angina. ICD-10 flag: R00.0 tachycardia, I10 hypertension.",
        "dx_b": "Chest pain — possible heart attack. Need more tests.",
        # treatment_plan
        "tp_a": "1. Continuous cardiac monitoring. 2. Aspirin 300mg PO stat, hold thienopyridine pending cath decision. 3. Serial troponin at 3h and 6h. 4. IV access + bloods: FBC, U&E, LFT, coagulation. 5. Cardiology referral if troponin positive. 6. NPO for potential intervention.",
        "tp_b": "Monitor heart, give aspirin, run blood tests, call cardiology if needed.",
        # discharge_summary
        "ds_a": "ADMISSION SUMMARY — 62M admitted for rule-out ACS. Presenting complaint: 3h chest pain with diaphoresis and dyspnoea. Examination: haemodynamically stable, BP 148/92, HR 96. Investigations: ECG shows ST depression V4-V6; troponin pending. Plan: continuous monitoring, antiplatelet therapy initiated, serial biomarkers, cardiology review. Disposition: CCU pending troponin result.",
        "ds_b": "Patient admitted with chest pain. On monitoring. Awaiting test results.",
    },
    {
        "label": "type2-diabetes-management",
        "patient": "54F, T2DM x 8yrs. HbA1c 9.2%. On metformin 1g BD. Complains of fatigue and polyuria. BMI 31. BP 138/86. Microalbuminuria on last urine dip.",
        "sx_a": "Symptoms: fatigue, polyuria. PMH: T2DM 8 years. Current meds: metformin 1g BD. Vitals: BMI 31, BP 138/86. Labs: HbA1c 9.2%, microalbuminuria positive.",
        "sx_b": "Tiredness and frequent urination. Diabetic, overweight.",
        "dx_a": "E11.65 – T2DM with hyperglycaemia (HbA1c 9.2%, target <7%). Complication flags: N18.3 CKD stage 3 risk (microalbuminuria), I10 hypertension. Consider SGLT2i for cardio-renal benefit.",
        "dx_b": "Poorly controlled diabetes. High blood sugar.",
        "tp_a": "1. Intensify: add SGLT2 inhibitor (empagliflozin 10mg OD) for HbA1c reduction and renal protection. 2. Continue metformin 1g BD. 3. ACE inhibitor (ramipril 5mg OD) for microalbuminuria and BP. 4. Repeat HbA1c in 3 months. 5. eGFR and urine ACR. 6. Refer to diabetes dietitian. 7. Foot and eye screening due.",
        "tp_b": "Add another diabetes tablet. Recheck bloods in 3 months. Diet advice.",
        "ds_a": "REVIEW SUMMARY — 54F with poorly controlled T2DM (HbA1c 9.2%). Symptoms of hyperglycaemia: fatigue, polyuria. Complications: microalbuminuria suggesting early diabetic nephropathy; hypertension. Plan: SGLT2 inhibitor added for dual glycaemic and renal benefit; ACE inhibitor initiated; dietary referral arranged. Follow-up: 3-month HbA1c, eGFR, and ACR. Screening overdue — referrals sent.",
        "ds_b": "Diabetes not well controlled. New tablet added. Come back in 3 months.",
    },
    {
        "label": "post-op-knee-replacement",
        "patient": "71M, day 3 post right total knee replacement. Mild wound ooze, no signs of infection. Pain 5/10, well-controlled on oxycodone SR + paracetamol. Physio commenced. DVT prophylaxis ongoing.",
        "sx_a": "Post-op day 3: right TKR. Pain: 5/10 (well-controlled). Wound: mild ooze, no erythema/warmth/discharge. Mobility: physio commenced, partial weight-bearing. DVT prophylaxis: ongoing (LMWH).",
        "sx_b": "Post knee op, day 3. Some wound leaking, pain okay.",
        "dx_a": "Z96.651 – Right TKR in situ. Post-op status: uncomplicated to date. Monitor: wound integrity (rule out haematoma vs infection), VTE risk (high post arthroplasty). Current analgesia effective.",
        "dx_b": "Knee replacement patient recovering normally.",
        "tp_a": "1. Continue oxycodone SR 10mg BD + paracetamol 1g QDS. Step down to oral analgesia ladder day 5. 2. Dressing change daily — reassess wound ooze; swab if purulent. 3. LMWH (enoxaparin 40mg SC OD) continue for 35 days total per NICE NG89. 4. Physiotherapy BD — range of motion and gait training. 5. Bloods: FBC day 4 (haemoglobin trend). 6. Target discharge day 4-5 with community physio referral.",
        "tp_b": "Keep painkillers going, change dressing, continue blood thinners, physio daily.",
        "ds_a": "POST-OP SUMMARY — 71M, day 3 right TKR. Uncomplicated recovery. Pain controlled on opioid + paracetamol combination. Wound: mild ooze only — no signs of infection. DVT prophylaxis in progress per NICE NG89. Physiotherapy commenced; partial weight-bearing achieved. Plan: step-down analgesia day 5, daily wound review, discharge day 4-5 with community physio and GP follow-up letter.",
        "ds_b": "Knee op patient doing well. Going home soon. Follow-up with GP.",
    },
    {
        "label": "anxiety-depression-review",
        "patient": "34F, known GAD and MDD. Presenting for 6-week medication review. On sertraline 100mg OD x 12 weeks. PHQ-9: 11 (moderate). GAD-7: 14 (moderate-severe). Reports improved sleep, still struggling with concentration and low motivation.",
        "sx_a": "Mental health review: GAD + MDD. Medication: sertraline 100mg OD (12 weeks). PHQ-9: 11/27 (moderate depression). GAD-7: 14/21 (moderate-severe anxiety). Response: partial — sleep improved, concentration and motivation persisting.",
        "sx_b": "Anxiety and depression, on antidepressants. Feeling a bit better but not great.",
        "dx_a": "F41.1 GAD (GAD-7 14 — moderate-severe). F32.1 MDD moderate (PHQ-9 11). Partial treatment response at 12 weeks. Consider: dose optimisation vs augmentation vs therapy referral.",
        "dx_b": "Anxiety and depression, partially responding to sertraline.",
        "tp_a": "1. Increase sertraline to 150mg OD — partial response at 100mg, not at maximum dose. 2. Provide psychoeducation on delayed full response (4-6 weeks). 3. Refer for CBT — NICE CG90 recommends combined therapy + medication for moderate-severe. 4. Safety plan reviewed — no active SI. 5. Occupational health referral if work impairment. 6. Repeat PHQ-9/GAD-7 at 6-week review.",
        "tp_b": "Increase dose slightly. Suggest therapy. Check in again in 6 weeks.",
        "ds_a": "MENTAL HEALTH REVIEW — 34F, GAD + MDD. Partial response to sertraline 100mg at 12 weeks (PHQ-9 11, GAD-7 14). Positive: sleep improved. Persisting: concentration deficit, low motivation. Plan: dose increase to 150mg OD; CBT referral initiated per NICE CG90; safety plan reviewed and documented; occupational health referral offered. Review in 6 weeks with repeat validated scales.",
        "ds_b": "Patient doing a bit better on antidepressants. Dose increased. Therapy suggested.",
    },
    {
        "label": "hypertension-annual-review",
        "patient": "58M, essential hypertension x 10yrs. On amlodipine 10mg + ramipril 10mg. Home BP diary: avg 152/94. Clinic BP: 158/96. Smoker (10/day). Total cholesterol 5.8, LDL 3.9. BMI 27.",
        "sx_a": "Hypertension annual review. Medications: amlodipine 10mg OD + ramipril 10mg OD. BP control: inadequate — home avg 152/94, clinic 158/96. Risk factors: smoking 10/day, LDL 3.9 mmol/L, total cholesterol 5.8. BMI 27.",
        "sx_b": "Blood pressure still high despite medication. Smoker.",
        "dx_a": "I10 – Essential hypertension, uncontrolled (target <130/80 per NICE NG136). QRISK3 elevated (smoking + hyperlipidaemia + age). E78.5 hyperlipidaemia. Therapeutic intensification required.",
        "dx_b": "High blood pressure not well controlled. High cholesterol.",
        "tp_a": "1. Add indapamide 1.5mg MR OD (step 3 per NICE NG136 — CCB + ACEi + thiazide-like). 2. Initiate atorvastatin 20mg ON (QRISK3 >10%, NICE threshold). 3. Smoking cessation referral + NRT prescription. 4. Home BP monitoring — target diary for 2 weeks. 5. Repeat bloods: U&E (ACEi + thiazide interaction), LFTs (statin baseline). 6. 4-week review.",
        "tp_b": "Add another BP tablet. Start cholesterol tablet. Stop smoking advice.",
        "ds_a": "ANNUAL REVIEW — 58M, uncontrolled essential hypertension on dual therapy. BP remains above target (158/96 clinic). Risk: QRISK3 elevated by smoking and LDL 3.9. Plan: third-line antihypertensive added (indapamide 1.5mg MR per NICE NG136 step 3); statin initiated; smoking cessation referral placed. Safety bloods requested. 4-week review booked.",
        "ds_b": "BP still too high. Added new tablet and cholesterol treatment. Told to stop smoking.",
    },
    {
        "label": "paediatric-febrile-illness",
        "patient": "3yr old F, brought by parent. Temperature 39.2°C for 24h. Mild cough, runny nose. Alert, playful, drinking well. No rash. Throat mildly red, no tonsillar exudate. Ears normal. HR 118, RR 24, SpO2 98%.",
        "sx_a": "Paediatric presentation: 3F. Fever 39.2°C x 24h. Associated: cough, coryza. Alert and playful, hydrated well. Examination: mild pharyngeal erythema, no exudate, no rash, normal ears. Vitals: HR 118, RR 24, SpO2 98% — within normal paediatric limits.",
        "sx_b": "Toddler with fever and cold symptoms. Looks okay.",
        "dx_a": "J06.9 – Acute URTI, viral (most likely). No bacterial focus identified (FeverPAIN score 1). No red flags (NICE NG143): alert, SpO2 normal, drinking well, no rash, no neck stiffness. Safety-netting required.",
        "dx_b": "Viral cold, nothing serious found.",
        "tp_a": "1. No antibiotics indicated — viral URTI, FeverPAIN 1 (NICE NG143). 2. Antipyretics: paracetamol 240mg QDS PRN (weight-based 15mg/kg). Ibuprofen 100mg TDS PRN if persistent. 3. Adequate fluid intake — encourage oral fluids; hospital if <50% normal intake. 4. Safety-net: return if temp >40°C, rash, difficulty breathing, inconsolable, or not improving 72h. 5. No investigations required.",
        "tp_b": "No antibiotics needed. Give Calpol. Bring back if gets worse.",
        "ds_a": "PAEDIATRIC NOTE — 3F, 24h fever with URTI symptoms. No bacterial focus (pharynx mildly red, no exudate; ears normal). Vitals appropriate for age — no red flags per NICE NG143. Diagnosis: viral URTI. Management: weight-based antipyretics, fluid encouragement, safety-net advice given to parent (documented). No antibiotics. No investigations. Return criteria explained.",
        "ds_b": "Viral illness. No antibiotics. Safety netting done. Follow up if worse.",
    },
    {
        "label": "stroke-tia-follow-up",
        "patient": "68M, 3 weeks post confirmed TIA (ABCD2 score 5). Started on aspirin + clopidogrel dual antiplatelet. Carotid doppler: 40% right ICA stenosis. Echo: no cardioembolic source. On atorvastatin 80mg + ramipril.",
        "sx_a": "Post-TIA follow-up (3 weeks). ABCD2 score: 5 (high risk). Dual antiplatelet: aspirin + clopidogrel. Investigations: carotid Doppler — 40% right ICA stenosis (non-significant); echo — no cardioembolic source. Meds: atorvastatin 80mg, ramipril.",
        "sx_b": "Patient had a mini-stroke 3 weeks ago. On blood thinners and statins.",
        "dx_a": "G45.9 – TIA (ABCD2 5, high recurrence risk). Aetiology: likely large vessel atherosclerotic (40% ICA stenosis) — non-surgical threshold but surveillance required. No AF detected. Risk factor burden: hypertension, dyslipidaemia.",
        "dx_b": "TIA, high risk. Atherosclerosis likely cause.",
        "tp_a": "1. Dual antiplatelet (aspirin 75mg + clopidogrel 75mg) — continue for 21 days total from event, then clopidogrel monotherapy per POINT trial protocol. 2. Atorvastatin 80mg — continue, LDL target <1.8 mmol/L (ESC 2021). 3. Ramipril — continue, BP target <130/80. 4. Repeat carotid Doppler in 6 months — 40% stenosis non-surgical but monitor for progression. 5. BP and lipid bloods in 6 weeks. 6. Driving licence DVLA notification — advise no driving for 1 month post-TIA.",
        "tp_b": "Continue all medications. Stop dual antiplatelet soon and switch to one tablet. Check bloods. No driving for a month.",
        "ds_a": "TIA FOLLOW-UP — 68M, 3 weeks post high-risk TIA (ABCD2 5). Investigations complete: non-significant carotid stenosis (40% R-ICA), no cardioembolic source. Dual antiplatelet therapy on schedule — transition to monotherapy (clopidogrel) at 21-day mark per POINT protocol. Statin and antihypertensive optimised. DVLA advice documented. 6-month carotid surveillance booked. Bloods in 6 weeks.",
        "ds_b": "TIA patient reviewed. Meds going well. Told about driving. Follow up in 6 months.",
    },
    {
        "label": "copd-exacerbation",
        "patient": "72M, COPD GOLD III. Presenting with 4-day worsening dyspnoea, increased yellow sputum, mild wheeze. SpO2 88% on air (baseline 91%). Temp 37.8°C. CXR: no consolidation. CRP 68.",
        "sx_a": "COPD exacerbation: 72M GOLD III. Duration: 4 days. Symptoms: worsening dyspnoea, purulent sputum, wheeze. SpO2 88% (below personal best 91%). Temp 37.8°C. CXR: hyperinflation, no consolidation. CRP 68 (elevated, suggests bacterial trigger).",
        "sx_b": "COPD patient breathing worse, yellow phlegm, SpO2 dropping.",
        "dx_a": "J44.1 – COPD exacerbation (moderate-severe). Trigger: likely bacterial (purulent sputum, CRP 68, low-grade pyrexia). No pneumonia on CXR. GOLD III baseline — high exacerbation risk patient. Hospital admission indicated (SpO2 below personal best, unable to manage at home).",
        "dx_b": "COPD flare-up, probably infected. Needs admission.",
        "tp_a": "1. Controlled O2 therapy — target SpO2 88-92% (COPD hypercapnic risk per BTS). 2. Nebulised salbutamol 2.5mg + ipratropium 500mcg Q4H. 3. Prednisolone 30mg OD x 5 days (NICE NG115). 4. Antibiotics: amoxicillin 500mg TDS x 5 days (purulent sputum, first-line per BTS). 5. Sputum culture. 6. ABG on admission — assess for hypercapnia / NIV threshold. 7. VTE prophylaxis (LMWH). 8. Pulmonary rehab referral post-discharge.",
        "tp_b": "Oxygen carefully, nebulisers, steroids and antibiotics. Admit. ABG if needed.",
        "ds_a": "ADMISSION — 72M GOLD III COPD moderate-severe exacerbation. Likely bacterial trigger (purulent sputum, CRP 68). No pneumonia. Admitted for: controlled O2 (target 88-92%), nebulised bronchodilators, prednisolone 30mg x 5d, amoxicillin 5d (BTS first-line). ABG on admission. VTE prophylaxis. Pulmonary rehab referral to be arranged post-discharge. Sputum sent.",
        "ds_b": "COPD patient admitted with flare. On oxygen, nebs, steroids, antibiotics.",
    },
    {
        "label": "antenatal-28-week-check",
        "patient": "29F, G1P0, 28+2 weeks. Routine antenatal. BP 118/74. Urinalysis: trace protein. Fundal height: 27cm. FHR: 146bpm. OGTT result: fasting 4.8, 2h 7.6 (normal). Hb 10.8 (mild anaemia).",
        "sx_a": "Antenatal review: 29F G1P0, 28+2 weeks. BP 118/74 (normal). Urinalysis: trace protein (re-check needed). Fundal height: 27cm (appropriate for dates). FHR: 146bpm (normal). OGTT: fasting 4.8, 2h 7.6 — GDM excluded. Hb 10.8 g/dL — mild iron-deficiency anaemia.",
        "sx_b": "28-week antenatal check. BP fine. Trace protein in urine. Slightly anaemic.",
        "dx_a": "Z34.22 – Supervision normal pregnancy 28 weeks. D50 – Iron deficiency anaemia (Hb 10.8; NICE threshold <11g/dL in 2nd trimester). Trace proteinuria: not diagnostic of pre-eclampsia alone (BP normal) — repeat MSU to exclude UTI and monitor.",
        "dx_b": "Normal pregnancy. Iron levels low. Protein in urine worth watching.",
        "tp_a": "1. Iron supplementation: ferrous sulfate 200mg BD (increase from standard 200mg OD — Hb 10.8 below trimester threshold). 2. Repeat MSU — exclude UTI (trace proteinuria may be contamination). 3. Baseline BP trend documented; repeat at 30-week check. 4. Refer to community midwife for kick chart and growth scan at 32 weeks. 5. GTT not required — OGTT passed. 6. Whooping cough vaccination due (28-32 weeks).",
        "tp_b": "Iron tablets. Repeat urine test. Whooping cough jab due. Scan at 32 weeks.",
        "ds_a": "ANTENATAL NOTE — 29F G1P0, 28+2 weeks. BP normal; OGTT negative for GDM. Mild anaemia (Hb 10.8) — ferrous sulfate increased. Trace proteinuria — MSU sent to exclude UTI; BP normal so pre-eclampsia less likely but monitoring documented. Fundal height and FHR appropriate. Pertussis vaccine discussed and scheduled. 32-week growth scan and next community midwife review arranged.",
        "ds_b": "28-week check done. Anaemia being treated. Urine being rechecked. Next scan at 32 weeks.",
    },
    {
        "label": "renal-colic-acute",
        "patient": "41M, severe loin-to-groin pain x 4h, unable to sit still, haematuria on urine dip. Temp 37.1°C. HR 104. BP 132/84. CT KUB: 5mm right ureteric calculus at vesicoureteric junction. No hydronephrosis.",
        "sx_a": "Acute renal colic: 41M. Pain: loin-to-groin, severe, colicky x 4h. Haematuria: present (urine dip). Vitals: afebrile (37.1°C), HR 104, BP 132/84. CT KUB: 5mm right ureteric stone at VUJ. No hydronephrosis, no fever — uncomplicated.",
        "sx_b": "Bad back pain going to groin. Blood in urine. Kidney stone on scan.",
        "dx_a": "N20.1 – Ureteric calculus (5mm R VUJ). Uncomplicated (no hydronephrosis, afebrile). 5mm stone at VUJ: ~50% spontaneous passage rate. Symptomatic management appropriate. Urology review if not passed in 4 weeks or if fever/obstruction develops.",
        "dx_b": "Kidney stone, right side. Should pass on its own.",
        "tp_a": "1. Analgesia: diclofenac 75mg IM stat (NSAID first-line for renal colic per EAU guidelines); PR diclofenac 100mg BD for 3 days; add paracetamol 1g QDS. 2. Medical expulsive therapy: tamsulosin 400mcg OD (alpha-blocker — EAU evidence B for stones ≥5mm). 3. High fluid intake: >2.5L/day. 4. Urine strainer (stone analysis). 5. Safety-net: A&E if fever, rigors, severe vomiting, or intractable pain (obstructed infected kidney is emergency). 6. Urology follow-up in 4 weeks + KUB X-ray.",
        "tp_b": "Painkillers, drink lots of fluids, pass it at home hopefully. See urology if not passed.",
        "ds_a": "ACUTE RENAL COLIC — 41M, 5mm right ureteric stone at VUJ. Uncomplicated (afebrile, no hydronephrosis). Conservative management: NSAID analgesia, tamsulosin MET commenced (EAU guideline for ≥5mm), hydration advice. Stone strainer provided for analysis. Emergency return criteria given (fever + loin pain = infected obstruction, surgical emergency). Urology follow-up in 4 weeks + imaging to confirm passage.",
        "ds_b": "Kidney stone patient. Pain managed. Tablets to help pass it. Urology follow-up.",
    },
    {
        "label": "lower-back-pain-mechanical",
        "patient": "38F, 6-week history of lower back pain after lifting. No red flags: no night sweats, no weight loss, no bladder/bowel symptoms, no saddle anaesthesia. Straight leg raise negative bilaterally. Mild paravertebral muscle spasm on examination.",
        "sx_a": "Lower back pain: 38F, 6 weeks post-lifting injury. Red flag screen: negative (no fever, weight loss, bladder/bowel dysfunction, saddle anaesthesia). Neuro: SLR negative bilaterally. Examination: paravertebral muscle spasm, no neurological deficit. Duration: subacute (>6 weeks — approaching chronic threshold).",
        "sx_b": "Back pain for 6 weeks. No red flags. Muscle spasm on examination.",
        "dx_a": "M54.5 – Low back pain, mechanical (subacute). No features of radiculopathy (negative SLR, no dermatomal deficit). No red flags to mandate imaging per NICE NG59. Approaching chronic LBP — early active rehabilitation priority.",
        "dx_b": "Mechanical back pain. No serious cause.",
        "tp_a": "1. No imaging at this stage — NICE NG59: do not routinely offer MRI for non-specific LBP without red flags. 2. NSAIDs: naproxen 500mg BD x 7 days (with omeprazole 20mg gastroprotection). 3. Physiotherapy referral — active exercise programme (evidence: superior to passive treatment for subacute LBP). 4. Advise: stay active, avoid prolonged bed rest. 5. Occupational health referral if work-related lifting risk. 6. Reassess at 12 weeks — consider psychosocial screening (STarT Back Tool) if persists.",
        "tp_b": "No scan needed. Anti-inflammatories and physio. Stay active.",
        "ds_a": "BACK PAIN REVIEW — 38F, 6-week mechanical LBP post-lifting. Red flags excluded. No neurological deficit. No imaging indicated per NICE NG59. Plan: NSAID course with gastroprotection, physiotherapy referral (active exercise programme). Advised to remain active. Occupational health referral offered. Review at 12 weeks with STarT Back Tool if not resolving.",
        "ds_b": "Mechanical back pain. No scan. Physio and tablets. Review if still hurts.",
    },
    {
        "label": "migraine-new-diagnosis",
        "patient": "27F, 3-month history of unilateral throbbing headaches, 4-6h duration, nausea, phonophobia. No aura. Frequency: 3x/month. Paracetamol partially helpful. Normal neurological exam. No red flags.",
        "sx_a": "Migraine workup: 27F. Headache character: unilateral, throbbing, severe, 4-6h. Associated: nausea, phonophobia (no aura, no photophobia specifically noted). Frequency: 3x/month. Analgesia: paracetamol — partial response. Neurology: normal exam, no red flags.",
        "sx_b": "Headaches 3 times a month, one-sided, with nausea. Normal neuro exam.",
        "dx_a": "G43.009 – Migraine without aura (ICHD-3 criteria met: ≥5 attacks, 4-72h, unilateral, throbbing, moderate-severe, with nausea/phonophobia). 3 attacks/month — episodic, below prophylaxis threshold (≥4/month). Paracetamol inadequate — step up acute therapy.",
        "dx_b": "Migraine diagnosis. Needs better treatment.",
        "tp_a": "1. Acute: sumatriptan 50mg PO at onset (5HT1 agonist — first-line triptan per NICE NG150); take early in attack. Provide 6 tablets, assess at 4-week review. Anti-emetic: prochlorperazine 10mg PO PRN nausea. 2. Lifestyle: headache diary (frequency, triggers, duration). 3. No prophylaxis yet (3/month below threshold — reassess if ≥4). 4. Red flag counselling: seek urgent review for 'thunderclap', first-ever severe, fever + rash, or neurological deficit. 5. Review in 6-8 weeks.",
        "tp_b": "Try a triptan. Keep a headache diary. Prophylaxis if gets worse. Review in 6 weeks.",
        "ds_a": "NEW MIGRAINE DIAGNOSIS — 27F, 3/month migraine without aura (ICHD-3 criteria met). Paracetamol inadequate. Management: sumatriptan 50mg prescribed for acute attacks (NICE NG150 first-line); prochlorperazine for nausea. Headache diary initiated. Prophylaxis threshold not met (3/month). Red flag symptoms discussed and documented. Review 6-8 weeks with diary review — prophylaxis to be considered if frequency increases.",
        "ds_b": "Migraine confirmed. Triptan prescribed. Diary to be kept. Follow up in 6 weeks.",
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
    print("  FORKMARK HEALTHCARE DEMO SEEDER")
    print("  Clinical Note Summarization — 12 Cases × 4 Steps")
    print("═" * 65 + "\n")

    # 1 — Workflow
    print("[1/4] Creating workflow...")
    wf = api("post", "/api/workflows", {
        "name": "clinical-note-summarization",
        "description": "4-step clinical documentation pipeline: symptom extraction, diagnosis coding, treatment planning, and discharge summary generation.",
    })
    if not wf:
        wfs = api("get", "/api/workflows")
        wf  = next((w for w in (wfs or []) if w["name"] == "clinical-note-summarization"), None)
    if not wf:
        print("[error] Could not create or find workflow.")
        sys.exit(1)
    print(f"       workflow id: {wf['id']}\n")

    # 2 — Eval run
    print("[2/4] Creating eval run...")
    er = api("post", "/api/eval-runs", {
        "workflow_name": "clinical-note-summarization",
        "name": "Structured SOAP Prompt v2 vs Terse Prompt v1 — Clinical Notes",
        "description": "Evaluating whether a structured SOAP-format prompt produces safer, more complete clinical documentation than a terse summarisation prompt across 12 clinical specialties.",
        "branch_a_config": {"label": "Structured SOAP Prompt v2 (Baseline)", "model_id": "gpt-4o", "temperature": 0.1},
        "branch_b_config": {"label": "Terse Summary Prompt v1 (Challenger)", "model_id": "gpt-4o", "temperature": 0.1},
        "total_cases": len(CASES),
    })
    if not er:
        print("[error] Could not create eval run.")
        sys.exit(1)
    er_id = er["id"]
    print(f"       eval run id: {er_id}\n")

    # 3 — Seed comparisons
    print(f"[3/4] Seeding {len(CASES)} test cases (4 steps each)...")
    print()

    for i, c in enumerate(CASES):
        print(f"  [{i+1:02d}/{len(CASES)}] {c['label']}")

        run = api("post", "/api/sdk/runs", {
            "workflow_name":   "clinical-note-summarization",
            "input_data":      {"patient_note": c["patient"], "label": c["label"]},
            "eval_run_id":     er_id,
            "test_case_label": c["label"],
        })
        if not run:
            print("         [skip] run creation failed")
            continue
        run_id = run["id"]

        ba = api("post", "/api/sdk/branches", {
            "run_id": run_id, "name": "soap-prompt-v2", "model_id": "gpt-4o",
            "temperature": 0.1, "is_baseline": True,
        })
        bb = api("post", "/api/sdk/branches", {
            "run_id": run_id, "name": "terse-prompt-v1", "model_id": "gpt-4o",
            "temperature": 0.1, "is_baseline": False,
        })
        if not ba or not bb:
            print("         [skip] branch creation failed")
            continue

        steps = [
            ("symptom_extraction",  c["sx_a"],  c["sx_b"]),
            ("diagnosis_coding",    c["dx_a"],  c["dx_b"]),
            ("treatment_plan",      c["tp_a"],  c["tp_b"]),
            ("discharge_summary",   c["ds_a"],  c["ds_b"]),
        ]
        msg = [{"role": "user", "content": c["patient"]}]
        for idx, (step, out_a, out_b) in enumerate(steps):
            base_in = 90 + len(c["patient"]) // 4
            api("post", "/api/sdk/steps", {
                "run_id": run_id, "branch_id": ba["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_a,
                "model_id": "gpt-4o", "temperature": 0.1,
                "tokens_input": base_in, "tokens_output": len(out_a.split()),
                "latency_ms": 310 + idx * 55,
            })
            api("post", "/api/sdk/steps", {
                "run_id": run_id, "branch_id": bb["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_b,
                "model_id": "gpt-4o", "temperature": 0.1,
                "tokens_input": base_in, "tokens_output": len(out_b.split()),
                "latency_ms": 290 + idx * 50,
            })

        api("post", f"/api/sdk/runs/{run_id}/complete", {"status": "completed"})
        comp = api("post", "/api/sdk/comparisons", {
            "run_id": run_id,
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

    # 4 — Complete eval run
    print()
    print("[4/4] Completing eval run...")
    api("patch", f"/api/eval-runs/{er_id}/complete", {
        "status": "completed", "total_cases": len(CASES),
    })

    print()
    print("═" * 65)
    print("  HEALTHCARE DEMO READY")
    print("═" * 65)
    print()
    print("  Open Forkmark:  http://localhost:5173")
    print(f"  Eval Run ID:     {er_id}")
    print()
    print("  High-divergence cases to review:")
    print("  • chest-pain-rule-out-acs    — SOAP prompt adds ICD-10, drug doses")
    print("  • type2-diabetes-management  — SOAP adds SGLT2i rationale, targets")
    print("  • stroke-tia-follow-up       — SOAP adds POINT protocol, DVLA advice")
    print("  • copd-exacerbation          — SOAP adds BTS guidelines, NIV threshold")
    print()


if __name__ == "__main__":
    seed()
