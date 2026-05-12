"""Generate one long, multi-note TXT chart per patient from patients_raw.csv.

Each patient's .txt file contains a full set of clinical notes spanning their
stay: ED triage, ED physician evaluation, History & Physical, daily progress
notes, multiple nursing shift notes per day, specialist consult(s), an
imaging report, pharmacy med-rec, and a discharge summary. Note content is
diagnosis-aware and pulls vitals/labs/demographics from the structured row.

Run:
    python generate_notes.py
Output:
    patient_notes/PT00001.txt ... PT01000.txt
"""

from __future__ import annotations

import random
import re
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

SEED = 42
CSV_PATH = Path(__file__).parent / "patients_raw.csv"
OUT_DIR = Path(__file__).parent / "patient_notes"
LINE_WIDTH = 88

random.seed(SEED)

HOSPITALS = [
    "Riverside General Hospital",
    "St. Marian Medical Center",
    "Lakeside Regional Health",
    "Mercy Heights Hospital",
]

PROVIDERS = {
    "ed_md": [
        ("D. Alvarez, MD",   "Emergency Medicine"),
        ("T. Brennan, MD",   "Emergency Medicine"),
        ("P. Singh, DO",     "Emergency Medicine"),
    ],
    "hospitalist": [
        ("A. Chen, MD",      "Internal Medicine"),
        ("R. Patel, DO",     "Hospitalist"),
        ("M. Johnson, MD",   "Family Medicine"),
        ("K. Okafor, MD",    "Internal Medicine"),
        ("L. Nakamura, MD",  "Hospitalist"),
    ],
    "midlevel": [
        ("S. Rivera, NP",     "Hospital Medicine"),
        ("J. Andersen, PA-C", "Internal Medicine"),
        ("E. Whitman, NP",    "Hospital Medicine"),
    ],
    "rn": [
        "Maria T., RN", "Devon K., RN", "Priya A., RN", "Chris L., RN",
        "Hannah B., RN", "Jamal R., RN", "Erika S., RN", "Tomas P., RN",
        "Linh N., RN", "Aaron M., RN",
    ],
    "rad": [
        ("F. Goldstein, MD", "Radiology"),
        ("V. Ramirez, MD",   "Radiology"),
    ],
    "pharm": [
        ("R. Tanaka, PharmD",  "Clinical Pharmacy"),
        ("B. Owusu, PharmD",   "Clinical Pharmacy"),
    ],
}

CONSULT_SPECIALTY = {
    "E11.9": ("Endocrinology", "M. Salim, MD"),
    "I10":   (None, None),
    "J18.9": ("Pulmonology", "C. Vance, MD"),
    "N17.9": ("Nephrology", "H. Kowalski, MD"),
    "I50.9": ("Cardiology", "J. DeLuca, MD"),
    "J44.9": ("Pulmonology", "C. Vance, MD"),
    "A41.9": ("Infectious Disease", "N. Adeyemi, MD"),
    "K35.80":("General Surgery", "P. Rosenthal, MD"),
    "I63.9": ("Neurology", "Y. Tanaka, MD"),
    "E78.5": (None, None),
}

# =============================================================================
# Diagnosis-specific narrative content
# =============================================================================

DX = {
    "E11.9": {
        "label": "Type 2 diabetes mellitus, decompensated",
        "cc": "uncontrolled hyperglycemia and fatigue",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} with a longstanding history of type 2 "
            "diabetes mellitus who presents to the emergency department with several weeks "
            "of polyuria, polydipsia, blurred vision, and worsening fatigue. The patient "
            "reports inconsistent adherence to oral hypoglycemic agents over the last two "
            "months, citing cost and forgetfulness. Home fingerstick glucose readings have "
            "reportedly been in the 250 to 350 mg/dL range, occasionally higher. The "
            "patient denies chest pain, shortness of breath, abdominal pain, nausea, or "
            "vomiting. There is no history of recent infection, no fevers, and no urinary "
            "symptoms beyond increased frequency. The patient denies any focal neurologic "
            "deficits or altered mental status. Last hemoglobin A1c, obtained roughly six "
            "months ago, was reported as 9.4%. The patient was advised at that time to "
            "initiate basal insulin but declined."
        ),
        "hp_hpi": (
            "On further history, the patient endorses an unintentional weight loss of "
            "approximately 8 pounds over the past month. Appetite is preserved. Sleep "
            "has been disrupted by nocturia (3-4 times nightly). The patient lives alone, "
            "ambulates independently, and reports no recent hospitalizations. Family history "
            "is significant for type 2 diabetes in both parents and a sibling with coronary "
            "artery disease in their fifties. The patient has no known drug allergies."
        ),
        "pmh": [
            "Type 2 diabetes mellitus, diagnosed approximately 11 years ago",
            "Essential hypertension",
            "Hyperlipidemia",
            "Diabetic peripheral neuropathy, mild",
            "Stage 2 chronic kidney disease",
        ],
        "meds": [
            "Metformin 1000 mg PO BID (reports inconsistent adherence)",
            "Lisinopril 20 mg PO daily",
            "Atorvastatin 40 mg PO nightly",
            "Aspirin 81 mg PO daily",
        ],
        "exam": (
            "General: Alert, mildly fatigued, no acute distress. HEENT: Mucous membranes dry, "
            "oropharynx clear. Neck: Supple, no JVD. Cardiovascular: Regular rate and rhythm, "
            "normal S1/S2, no murmurs, rubs, or gallops. Lungs: Clear to auscultation "
            "bilaterally. Abdomen: Soft, non-tender, non-distended, normoactive bowel sounds. "
            "Extremities: No edema. Skin: Warm and dry, no rashes. Neurologic: Awake, alert, "
            "oriented to person, place, and time. Cranial nerves II-XII grossly intact. "
            "Decreased monofilament sensation bilaterally over the plantar surfaces of the "
            "feet, consistent with known peripheral neuropathy."
        ),
        "ed_workup": (
            "Initial labs notable for serum glucose elevated, anion gap within normal limits, "
            "bicarbonate 22, and negative serum ketones. Urinalysis with 3+ glucose and trace "
            "ketones. EKG shows normal sinus rhythm at 84 bpm without acute ischemic changes. "
            "Chest X-ray reviewed and unremarkable for acute cardiopulmonary process."
        ),
        "consult_focus": (
            "Endocrinology was consulted for assistance with insulin initiation and outpatient "
            "transition planning. Recommendations include initiation of basal insulin "
            "(glargine 0.2 units/kg/day), discontinuation of long-acting sulfonylureas if "
            "applicable, and re-engagement with a certified diabetes educator. Outpatient "
            "follow-up scheduled within two weeks of discharge."
        ),
        "imaging_kind": "Chest X-ray (PA and lateral)",
        "imaging_read": (
            "The cardiac silhouette is normal in size. The lungs are clear without focal "
            "consolidation, pleural effusion, or pneumothorax. Mediastinal contours are "
            "within normal limits. No acute osseous abnormality. IMPRESSION: No acute "
            "cardiopulmonary process."
        ),
        "plan_bullets": [
            "Hydration with isotonic IV fluids; reassess every 6 hours.",
            "Hold metformin temporarily; reinitiate when stable and renal function confirmed.",
            "Start basal insulin per endocrinology recommendations; sliding scale coverage.",
            "Repeat hemoglobin A1c, basic metabolic panel, and urine microalbumin.",
            "Diabetes education prior to discharge; provide glucometer training.",
            "Foot exam and ophthalmology referral on discharge.",
        ],
        "discharge_meds_add": [
            "Insulin glargine 16 units subcutaneously at bedtime",
            "Insulin lispro 4 units subcutaneously before meals (correctional sliding scale provided)",
        ],
        "discharge_instructions": (
            "Patient educated regarding signs and symptoms of hypoglycemia and hyperglycemia, "
            "proper insulin administration technique, glucometer use, and target fingerstick "
            "ranges. Patient verbalized understanding and demonstrated insulin injection "
            "technique under supervision. Follow-up with primary care within 7 days and "
            "endocrinology within 2 weeks. Return precautions discussed in detail."
        ),
    },
    "I10": {
        "label": "Hypertensive urgency secondary to medication non-adherence",
        "cc": "elevated blood pressure with headache",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} who presents to the emergency department "
            "after being noted to have blood pressure of 192/108 mmHg at an outpatient "
            "clinic visit earlier today. The patient reports a 3-day history of intermittent "
            "occipital headache, which they describe as a dull pressure sensation, worst in "
            "the morning. There has been associated mild dizziness when standing but no "
            "syncope. The patient denies vision changes, chest pain, palpitations, shortness "
            "of breath, focal weakness, or speech difficulty. There is no nausea or vomiting. "
            "On detailed medication review, the patient admits to having run out of "
            "antihypertensive medications approximately 2 weeks ago and has not refilled the "
            "prescriptions."
        ),
        "hp_hpi": (
            "The patient has a known history of essential hypertension, diagnosed seven "
            "years ago. Prior to running out of medications, blood pressures at home were "
            "reportedly well controlled in the 130s-140s/80s range. The patient denies any "
            "use of recreational substances, decongestants, or NSAIDs. Caffeine intake "
            "is approximately 2 cups of coffee daily. Diet is described as high in sodium. "
            "Family history is positive for hypertension and stroke in the patient's mother."
        ),
        "pmh": [
            "Essential hypertension",
            "Obesity (BMI 32)",
            "Mild obstructive sleep apnea (CPAP non-adherent)",
        ],
        "meds": [
            "Lisinopril 20 mg PO daily (out of medication x 2 weeks)",
            "Hydrochlorothiazide 25 mg PO daily (out of medication x 2 weeks)",
        ],
        "exam": (
            "General: Well-appearing, no acute distress. HEENT: Fundoscopic exam without "
            "papilledema, hemorrhages, or exudates. Neck: No carotid bruits. Cardiovascular: "
            "Regular rate and rhythm, prominent S2, no murmurs. Lungs: Clear bilaterally. "
            "Abdomen: Soft, non-tender, no abdominal bruits. Neurologic: Alert and oriented, "
            "cranial nerves intact, strength 5/5 in all extremities, sensation grossly "
            "intact, gait steady."
        ),
        "ed_workup": (
            "EKG shows normal sinus rhythm with criteria suggestive of left ventricular "
            "hypertrophy. Troponin is negative. BUN and creatinine are at the patient's "
            "baseline. Urinalysis shows trace protein. CT head without contrast obtained "
            "given headache; no acute intracranial process identified."
        ),
        "consult_focus": "No specialty consult required for this admission.",
        "imaging_kind": "CT head without contrast",
        "imaging_read": (
            "There is no acute intracranial hemorrhage, mass effect, or midline shift. The "
            "ventricles and sulci are age-appropriate in caliber. Gray-white matter "
            "differentiation is preserved. No acute infarct or evidence of edema. The "
            "calvarium and visualized paranasal sinuses are unremarkable. IMPRESSION: No "
            "acute intracranial abnormality."
        ),
        "plan_bullets": [
            "Restart lisinopril and hydrochlorothiazide at home doses.",
            "Add amlodipine 5 mg PO daily if SBP remains > 150 mmHg.",
            "Monitor blood pressure every 4 hours.",
            "Pharmacy-led medication reconciliation and adherence counseling.",
            "Dietary counseling regarding sodium reduction.",
            "PCP follow-up within 7 days; consider home BP monitoring.",
        ],
        "discharge_meds_add": [
            "Lisinopril 20 mg PO daily",
            "Hydrochlorothiazide 25 mg PO daily",
            "Amlodipine 5 mg PO daily (new)",
        ],
        "discharge_instructions": (
            "Patient counseled on importance of medication adherence. A 90-day supply has "
            "been arranged and the patient was enrolled in the pharmacy refill reminder "
            "program. Patient instructed to monitor home BP twice daily and to seek "
            "emergency care for SBP > 180, severe headache, vision changes, chest pain, "
            "or any focal neurologic symptoms."
        ),
    },
    "J18.9": {
        "label": "Community-acquired pneumonia, right lower lobe",
        "cc": "productive cough, fever, and shortness of breath",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} presenting with 4 days of progressively "
            "worsening productive cough with thick yellow-green sputum, subjective fevers "
            "with measured home temperatures up to 101.8 degrees Fahrenheit, and exertional "
            "dyspnea. The patient also reports right-sided pleuritic chest pain that is "
            "worse with deep inspiration and coughing. There has been associated fatigue, "
            "decreased appetite, and one episode of rigors yesterday evening. The patient "
            "denies hemoptysis, recent travel, known sick contacts, or recent hospitalization. "
            "No history of aspiration events. Influenza-like illness was prevalent at the "
            "patient's workplace approximately one week ago."
        ),
        "hp_hpi": (
            "The patient is up to date with the 23-valent pneumococcal polysaccharide vaccine "
            "as of two years ago. Influenza vaccination this season is uncertain per patient "
            "report. Lives independently and works as documented in the social history below. "
            "Functional status at baseline is excellent without limitation."
        ),
        "pmh": [
            "Mild persistent asthma",
            "Seasonal allergic rhinitis",
        ],
        "meds": [
            "Albuterol HFA, 2 puffs every 4 hours PRN",
            "Fluticasone-salmeterol DPI, 1 inhalation BID",
            "Loratadine 10 mg PO daily",
        ],
        "exam": (
            "General: Mildly ill-appearing, breathing slightly labored. Vitals as documented. "
            "HEENT: Mucous membranes moist, oropharynx without exudate. Neck: Supple. "
            "Lungs: Coarse crackles auscultated at the right lower lung base with associated "
            "bronchial breath sounds and dullness to percussion. Mild wheezing on the right. "
            "Cardiovascular: Tachycardic but regular, no murmurs. Abdomen: Benign. "
            "Extremities: No edema or calf tenderness. SpO2 92% on room air, improving to "
            "96% on 2L nasal cannula."
        ),
        "ed_workup": (
            "CBC with leukocytosis to 14.2 with left shift. Procalcitonin elevated. Lactate "
            "normal. Influenza A/B and SARS-CoV-2 PCR pending. Sputum and blood cultures "
            "obtained. Chest X-ray demonstrates a right lower lobe infiltrate."
        ),
        "consult_focus": (
            "Pulmonology was consulted given hypoxemia and underlying asthma. Recommendations "
            "include continued IV antibiotics per institutional CAP pathway, scheduled "
            "albuterol-ipratropium nebulizers every 6 hours, continued inhaled corticosteroid, "
            "and incentive spirometry. Repeat chest imaging in 6-8 weeks following discharge "
            "is advised to confirm resolution."
        ),
        "imaging_kind": "Chest X-ray (PA and lateral)",
        "imaging_read": (
            "There is a focal area of airspace opacity within the right lower lobe with "
            "obscuration of the right hemidiaphragm, consistent with consolidation. No "
            "pleural effusion is identified. No pneumothorax. The cardiac silhouette is "
            "normal in size. IMPRESSION: Right lower lobe pneumonia."
        ),
        "plan_bullets": [
            "IV ceftriaxone 1 g daily plus azithromycin 500 mg daily x 5 days.",
            "Supplemental oxygen as needed to maintain SpO2 > 92%.",
            "Scheduled bronchodilator nebulizer treatments.",
            "Acetaminophen for fever control; avoid NSAIDs.",
            "DVT prophylaxis with enoxaparin 40 mg subcutaneously daily.",
            "Repeat chest imaging in 6-8 weeks post-discharge.",
        ],
        "discharge_meds_add": [
            "Oral cefpodoxime 200 mg PO BID x 3 additional days to complete therapy",
            "Continue home inhalers as previously prescribed",
        ],
        "discharge_instructions": (
            "Patient educated on signs of worsening infection including recurrent fever, "
            "increasing dyspnea, hemoptysis, and chest pain. Instructed to complete "
            "antibiotic course, maintain adequate hydration, and use incentive spirometer "
            "10 times per hour while awake. Follow-up with primary care in 5-7 days."
        ),
    },
    "N17.9": {
        "label": "Acute kidney injury, likely multifactorial",
        "cc": "decreased urine output and lower extremity edema",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} who presents with a 48-hour history of "
            "decreased urine output and new bilateral lower extremity swelling. The patient "
            "reports having started over-the-counter ibuprofen approximately 10 days ago for "
            "chronic low back pain, taking up to 800 mg every 6 hours. There has been "
            "associated mild nausea and decreased appetite. The patient denies hematuria, "
            "dysuria, urinary frequency, or fevers. There is no history of recent vomiting "
            "or diarrhea. The patient denies any prior diagnosis of kidney disease."
        ),
        "hp_hpi": (
            "The patient has a long history of chronic mechanical low back pain managed "
            "previously with physical therapy and acetaminophen. NSAIDs were initiated "
            "without provider guidance. The patient also takes lisinopril for hypertension. "
            "Volume status assessment in the ED was equivocal, leading to admission for "
            "ongoing evaluation and management."
        ),
        "pmh": [
            "Essential hypertension",
            "Chronic mechanical low back pain",
            "Hyperlipidemia",
        ],
        "meds": [
            "Lisinopril 20 mg PO daily (held on admission)",
            "Atorvastatin 20 mg PO nightly",
            "Ibuprofen 800 mg PO every 6 hours (recently self-initiated, now discontinued)",
        ],
        "exam": (
            "General: Alert, no acute distress. HEENT: Unremarkable. Neck: JVP not elevated. "
            "Cardiovascular: Regular rate and rhythm, no murmurs. Lungs: Clear bilaterally. "
            "Abdomen: Soft, non-tender, no flank tenderness, no costovertebral angle "
            "tenderness. Extremities: 2+ pitting edema bilateral lower extremities to mid-shin. "
            "Skin: Warm, well-perfused."
        ),
        "ed_workup": (
            "Creatinine elevated above patient's baseline. BUN/Cr ratio suggests intrinsic "
            "process. Urinalysis demonstrates muddy brown casts on microscopy. FENa is "
            "consistent with intrinsic renal injury. Renal ultrasound shows no hydronephrosis. "
            "Bladder scan shows minimal residual."
        ),
        "consult_focus": (
            "Nephrology was consulted. Diagnostic impression is acute tubular necrosis "
            "secondary to NSAID exposure, potentially compounded by ACE-inhibitor use. "
            "Recommendations include holding all nephrotoxic agents, cautious volume "
            "resuscitation, strict intake and output documentation, daily basic metabolic "
            "panel, urine electrolytes, and serial creatinine monitoring. If creatinine "
            "fails to improve or worsens, consider renal biopsy."
        ),
        "imaging_kind": "Renal ultrasound",
        "imaging_read": (
            "The kidneys are normal in size and contour bilaterally. There is no "
            "hydronephrosis, mass, or nephrolithiasis. The bladder is partially distended "
            "without focal lesion. No perinephric fluid collection. IMPRESSION: No "
            "obstructive uropathy."
        ),
        "plan_bullets": [
            "Hold all NSAIDs and ACE-inhibitor.",
            "Cautious IV fluid administration; reassess volume status every 6 hours.",
            "Strict intake and output recording.",
            "Trend basic metabolic panel daily until creatinine returns to baseline.",
            "Renal diet (low potassium, low phosphorus).",
            "Outpatient nephrology follow-up within 2 weeks of discharge.",
        ],
        "discharge_meds_add": [
            "Avoid NSAIDs indefinitely",
            "Hold lisinopril pending nephrology re-evaluation",
        ],
        "discharge_instructions": (
            "Patient educated on the dangers of NSAID use given underlying kidney injury. "
            "Alternative analgesia with scheduled acetaminophen and topical agents discussed. "
            "Patient instructed to maintain adequate oral hydration and to return for "
            "decreased urination, swelling, or symptoms of uremia."
        ),
    },
    "I50.9": {
        "label": "Acute decompensated heart failure",
        "cc": "progressive dyspnea, orthopnea, and lower extremity edema",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} with known heart failure with reduced "
            "ejection fraction (last documented EF 30-35%) presenting with two weeks of "
            "progressive dyspnea on exertion, orthopnea now requiring 3 pillows, and an "
            "8-pound weight gain. The patient endorses dietary indiscretion during recent "
            "holidays with high sodium intake. The patient self-decreased the diuretic dose "
            "approximately 10 days ago due to perceived dizziness. There is no chest pain, "
            "palpitations, or syncope. The patient denies fevers or cough productive of "
            "sputum."
        ),
        "hp_hpi": (
            "The patient has been managed by an outpatient cardiologist with guideline-"
            "directed medical therapy. The patient is status post coronary artery bypass "
            "grafting 6 years ago. Last echocardiogram, 4 months ago, demonstrated an "
            "ejection fraction of 32% with global hypokinesis. The patient has a permanent "
            "pacemaker but is not a candidate for ICD per cardiology."
        ),
        "pmh": [
            "Heart failure with reduced ejection fraction",
            "Coronary artery disease, status post CABG x 3",
            "Atrial fibrillation, on anticoagulation",
            "Hypertension",
            "Type 2 diabetes mellitus",
        ],
        "meds": [
            "Furosemide 40 mg PO daily (self-decreased from 80 mg)",
            "Carvedilol 25 mg PO BID",
            "Sacubitril-valsartan 49/51 mg PO BID",
            "Spironolactone 25 mg PO daily",
            "Apixaban 5 mg PO BID",
            "Atorvastatin 40 mg PO nightly",
        ],
        "exam": (
            "General: Mildly dyspneic at rest, able to speak in full sentences. JVP elevated "
            "to approximately 12 cm above the sternal angle. Cardiovascular: Irregularly "
            "irregular rhythm, no murmurs appreciated, displaced point of maximal impulse. "
            "Lungs: Bibasilar crackles extending one-third up the lung fields. Abdomen: "
            "Soft, non-tender, no hepatojugular reflux assessed but liver edge palpable 2 cm "
            "below the costal margin. Extremities: 2+ pitting edema to mid-shin bilaterally."
        ),
        "ed_workup": (
            "BNP significantly elevated above prior baseline. Troponin negative. Chest X-ray "
            "consistent with pulmonary vascular congestion and mild cephalization. EKG with "
            "atrial fibrillation at controlled rate. Basic metabolic panel with mild "
            "hyponatremia and stable creatinine."
        ),
        "consult_focus": (
            "Cardiology was consulted. Recommendations include IV diuresis with a goal of "
            "net negative 1-2 liters per day, daily weights, strict intake and output "
            "monitoring, continuation of guideline-directed medical therapy, repeat "
            "echocardiogram during this admission to reassess EF, and consideration of "
            "advanced heart failure clinic enrollment given recurrent admissions."
        ),
        "imaging_kind": "Chest X-ray (portable)",
        "imaging_read": (
            "The cardiac silhouette is enlarged, similar to prior. There is interstitial "
            "edema with Kerley B lines. Small bilateral pleural effusions are noted, right "
            "greater than left. No focal consolidation. IMPRESSION: Findings consistent "
            "with pulmonary edema and small bilateral pleural effusions in the setting of "
            "congestive heart failure exacerbation."
        ),
        "plan_bullets": [
            "IV furosemide 80 mg twice daily initially; titrate to net negative 1-2 L/day.",
            "Daily weights, strict I/Os, fluid restriction 1.5 L/day.",
            "Continue carvedilol; hold sacubitril-valsartan if hypotension develops.",
            "Repeat echocardiogram during this admission.",
            "Dietitian consultation for low-sodium dietary counseling.",
            "Cardiac rehabilitation referral on discharge.",
        ],
        "discharge_meds_add": [
            "Furosemide 80 mg PO daily (resumed at full home dose)",
            "Continue all other home cardiac medications as previously prescribed",
        ],
        "discharge_instructions": (
            "Patient and caregiver counseled regarding daily weight monitoring, sodium "
            "restriction to less than 2 grams per day, fluid restriction to 1.5 liters per "
            "day, and importance of medication adherence. Provided with heart failure "
            "education materials. Instructed to call the heart failure clinic for weight "
            "gain greater than 3 pounds in 2 days or 5 pounds in a week."
        ),
    },
    "J44.9": {
        "label": "Acute exacerbation of chronic obstructive pulmonary disease",
        "cc": "increased dyspnea, productive cough, and sputum change",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} with a known history of severe COPD "
            "presenting with 5 days of increased dyspnea, productive cough, and change in "
            "sputum from clear to thick yellow. The patient reports using the rescue albuterol "
            "inhaler every 2 hours with minimal relief. There has been associated wheezing, "
            "chest tightness, and decreased exercise tolerance. The patient denies fevers, "
            "hemoptysis, chest pain, or pleurisy. There is no history of recent travel or sick "
            "contacts."
        ),
        "hp_hpi": (
            "The patient was last hospitalized for COPD exacerbation approximately 8 months "
            "ago. Spirometry from one year ago demonstrated severe airflow obstruction "
            "(GOLD stage 3). The patient is not on home oxygen but has been advised to "
            "consider it at the most recent pulmonology visit. Risk factor counseling has "
            "been provided at multiple encounters."
        ),
        "pmh": [
            "Chronic obstructive pulmonary disease, GOLD stage 3",
            "Hyperlipidemia",
            "Anxiety disorder",
        ],
        "meds": [
            "Tiotropium 18 mcg inhaled daily",
            "Albuterol HFA 2 puffs every 4 hours PRN",
            "Budesonide-formoterol inhaler BID",
            "Atorvastatin 20 mg PO nightly",
            "Sertraline 50 mg PO daily",
        ],
        "exam": (
            "General: Mildly tachypneic with audible wheezing. Pursed-lip breathing noted. "
            "Use of accessory muscles. HEENT: No JVD. Lungs: Diffuse expiratory wheezing "
            "with prolonged expiratory phase. Decreased air movement at the bases. "
            "Cardiovascular: Tachycardic, regular, no murmurs. Abdomen: Soft, non-tender. "
            "Extremities: No edema. SpO2 88% on room air, improving to 93% on 2 L nasal "
            "cannula."
        ),
        "ed_workup": (
            "ABG on room air demonstrates mild hypoxemia and compensated respiratory "
            "acidosis. CBC with mild leukocytosis. Procalcitonin pending. Chest X-ray shows "
            "hyperinflation without focal consolidation. Sputum culture obtained."
        ),
        "consult_focus": (
            "Pulmonology was consulted. Recommendations include continued bronchodilator "
            "therapy, systemic corticosteroids with a 5-day course of prednisone equivalent, "
            "empiric azithromycin for 5 days given purulent sputum, and supplemental oxygen "
            "titrated to SpO2 88-92%."
        ),
        "imaging_kind": "Chest X-ray (PA and lateral)",
        "imaging_read": (
            "The lungs are hyperinflated with flattening of the diaphragms. There is "
            "increased retrosternal lucency. No focal consolidation, pleural effusion, or "
            "pneumothorax. Cardiac silhouette is within normal limits. IMPRESSION: "
            "Findings consistent with chronic obstructive pulmonary disease. No acute "
            "infiltrate."
        ),
        "plan_bullets": [
            "Albuterol-ipratropium nebulizer every 4 hours, with PRN albuterol between.",
            "Methylprednisolone 60 mg IV, transition to oral prednisone taper.",
            "Empiric azithromycin 500 mg PO daily x 5 days.",
            "Supplemental oxygen to maintain SpO2 88-92%.",
            "Pulmonary rehabilitation referral on discharge.",
        ],
        "discharge_meds_add": [
            "Prednisone 40 mg PO daily x 5 days then taper",
            "Continue home inhalers",
        ],
        "discharge_instructions": (
            "Patient educated on COPD action plan, inhaler technique, and warning signs "
            "warranting return to care. Pulmonary rehabilitation enrollment discussed. "
            "Follow-up with pulmonology in 2 weeks."
        ),
    },
    "A41.9": {
        "label": "Sepsis, likely urinary source",
        "cc": "fevers, chills, and altered mental status",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} brought in by family with 48 hours of "
            "fevers, chills, generalized weakness, and progressive confusion. The patient "
            "lives at home and is normally independent in activities of daily living per "
            "the family. Over the past day, the patient has been increasingly somnolent "
            "and intermittently disoriented. There have been associated symptoms of "
            "dysuria and urinary frequency over the past 4 days. The family reports the "
            "patient has had decreased oral intake."
        ),
        "hp_hpi": (
            "The patient has a history of recurrent urinary tract infections, most recently "
            "treated 3 months ago with nitrofurantoin. The patient also has poorly "
            "controlled diabetes. ED triage vitals were notable for tachycardia, "
            "hypotension, and a fever of 102.3F. The sepsis bundle was activated promptly "
            "and the patient is being admitted to the medical intensive care unit for "
            "ongoing resuscitation and monitoring."
        ),
        "pmh": [
            "Recurrent urinary tract infections",
            "Type 2 diabetes mellitus, poorly controlled",
            "Hypertension",
            "Stage 3a chronic kidney disease",
        ],
        "meds": [
            "Metformin 1000 mg PO BID",
            "Glipizide 5 mg PO daily",
            "Lisinopril 20 mg PO daily (held on admission)",
            "Atorvastatin 40 mg PO nightly",
        ],
        "exam": (
            "General: Ill-appearing, mildly somnolent but arousable to voice. HEENT: Mucous "
            "membranes dry. Neck: Supple, no meningismus. Cardiovascular: Tachycardic, "
            "regular, no murmurs. Lungs: Clear bilaterally. Abdomen: Soft, mild suprapubic "
            "tenderness, no rebound or guarding. Costovertebral angle tenderness on the "
            "right. Extremities: No edema. Skin: Warm but mottled appearance on the lower "
            "extremities. Neurologic: Oriented to self only, follows simple commands, no "
            "focal deficits."
        ),
        "ed_workup": (
            "Initial lactate elevated. CBC with leukocytosis and bandemia. Urinalysis with "
            "large leukocyte esterase, positive nitrites, and many white blood cells. Urine "
            "and blood cultures obtained prior to antibiotic administration. Chest X-ray "
            "unremarkable for source. CT abdomen/pelvis pending."
        ),
        "consult_focus": (
            "Infectious Disease consulted given sepsis and recurrent urinary infections. "
            "Recommendations include empiric broad-spectrum antibiotics with piperacillin-"
            "tazobactam pending culture data, narrowing once sensitivities return, urology "
            "consultation if recurrence persists, and outpatient follow-up to address "
            "potential underlying anatomic or functional contributors."
        ),
        "imaging_kind": "CT abdomen and pelvis with contrast",
        "imaging_read": (
            "The kidneys are normal in size with mild perinephric stranding on the right, "
            "consistent with pyelonephritis. There is no abscess. The bladder is "
            "decompressed with a Foley catheter in place. No bowel obstruction or free air. "
            "IMPRESSION: Right pyelonephritis without complication. No abscess identified."
        ),
        "plan_bullets": [
            "Sepsis bundle: 30 mL/kg IV crystalloid bolus, repeat lactate at 4 hours.",
            "Empiric piperacillin-tazobactam 4.5 g IV every 8 hours pending cultures.",
            "Vasopressor support if MAP < 65 despite adequate volume resuscitation.",
            "ICU monitoring with hourly urine output goals.",
            "Hold ACE-inhibitor; monitor renal function closely.",
            "Diabetes management with insulin sliding scale; hold metformin while NPO.",
        ],
        "discharge_meds_add": [
            "Oral antibiotic to complete 14-day course pending culture sensitivities",
            "Outpatient urology referral",
        ],
        "discharge_instructions": (
            "Patient and family educated on signs of recurrent infection and the importance "
            "of completing the antibiotic course. Patient instructed to maintain adequate "
            "hydration and to seek urgent evaluation for recurrent fevers, flank pain, or "
            "altered mental status. Diabetic management plan reviewed and updated."
        ),
    },
    "K35.80": {
        "label": "Acute uncomplicated appendicitis",
        "cc": "right lower quadrant abdominal pain",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} presenting with approximately 18 hours of "
            "abdominal pain. The pain began as a vague periumbilical discomfort but has "
            "since migrated to the right lower quadrant and become sharp and persistent. "
            "Associated symptoms include nausea, one episode of non-bilious, non-bloody "
            "emesis, and complete loss of appetite. The patient denies diarrhea, "
            "constipation, hematochezia, dysuria, or vaginal discharge. The patient denies "
            "any prior similar episodes."
        ),
        "hp_hpi": (
            "The patient has no significant past surgical history. The last oral intake "
            "was a light lunch yesterday afternoon. The patient is generally healthy. "
            "There is no family history of inflammatory bowel disease or malignancy."
        ),
        "pmh": ["No significant past medical history"],
        "meds": ["No regular medications"],
        "exam": (
            "General: Patient lying supine, appears uncomfortable but in no acute distress. "
            "HEENT: Unremarkable. Cardiovascular: Regular rate and rhythm, no murmurs. "
            "Lungs: Clear bilaterally. Abdomen: Soft but tender to palpation at McBurney's "
            "point with voluntary guarding. Positive Rovsing sign. No rebound or rigidity. "
            "Bowel sounds present but diminished. Extremities: Unremarkable."
        ),
        "ed_workup": (
            "CBC with leukocytosis to 14.8 with left shift. Comprehensive metabolic panel "
            "unremarkable. Urinalysis without infection. Pregnancy test negative where "
            "applicable. CT abdomen and pelvis with IV contrast performed and reviewed."
        ),
        "consult_focus": (
            "General Surgery was consulted urgently. Recommendation is laparoscopic "
            "appendectomy this evening. The patient was made NPO, given preoperative "
            "antibiotics with piperacillin-tazobactam, and consent for surgery was obtained. "
            "Postoperative recovery anticipated to be uncomplicated."
        ),
        "imaging_kind": "CT abdomen and pelvis with IV contrast",
        "imaging_read": (
            "The appendix is dilated to 11 mm with surrounding fat stranding and a small "
            "amount of adjacent fluid. There is no appendicolith identified. No abscess or "
            "free air. The remainder of the abdomen and pelvis is unremarkable. "
            "IMPRESSION: Acute uncomplicated appendicitis."
        ),
        "plan_bullets": [
            "Laparoscopic appendectomy this evening.",
            "NPO; maintenance IV fluids.",
            "Preoperative antibiotic prophylaxis with piperacillin-tazobactam.",
            "Pain control with IV morphine PRN; transition to oral once tolerating PO.",
            "Advance diet postoperatively as tolerated.",
            "Anticipate discharge within 24-48 hours of surgery if uncomplicated.",
        ],
        "discharge_meds_add": [
            "Acetaminophen 500 mg PO every 6 hours scheduled",
            "Oxycodone 5 mg PO every 6 hours PRN x 3 days",
        ],
        "discharge_instructions": (
            "Patient educated on postoperative wound care, activity restrictions (no heavy "
            "lifting for 2 weeks), and signs of infection warranting return to care. "
            "Surgical clinic follow-up scheduled in 2 weeks for incision check and pathology "
            "review."
        ),
    },
    "I63.9": {
        "label": "Acute ischemic stroke",
        "cc": "acute onset right-sided weakness and slurred speech",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} whose spouse witnessed the abrupt onset of "
            "a right facial droop, right arm weakness, and slurred speech at approximately "
            "0830 this morning. The last known well time is documented as 0815, "
            "approximately 30 minutes prior to symptom onset. EMS was activated within "
            "10 minutes. On arrival to the ED, the patient was alert, following commands, "
            "but with persistent dysarthria and right hemiparesis. The patient denies "
            "headache, nausea, vomiting, or seizure activity. There has been no recent "
            "head trauma."
        ),
        "hp_hpi": (
            "The patient has known atrial fibrillation managed on rate control without "
            "anticoagulation due to a prior gastrointestinal bleeding episode. Cardiovascular "
            "risk factors include hypertension and hyperlipidemia. Additional risk factor "
            "exposures documented in social history below. Stroke alert was activated on "
            "arrival. Time-sensitive workup is in progress."
        ),
        "pmh": [
            "Atrial fibrillation",
            "Essential hypertension",
            "Hyperlipidemia",
            "Prior upper gastrointestinal bleed (peptic ulcer disease)",
        ],
        "meds": [
            "Metoprolol succinate 50 mg PO daily",
            "Lisinopril 10 mg PO daily",
            "Atorvastatin 40 mg PO nightly",
            "Pantoprazole 40 mg PO daily",
        ],
        "exam": (
            "General: Alert, mild distress related to symptoms. HEENT: Right facial droop "
            "with sparing of the forehead, consistent with central lesion. Speech is "
            "moderately dysarthric. Cardiovascular: Irregularly irregular rhythm, no "
            "murmurs. Lungs: Clear bilaterally. Abdomen: Benign. Neurologic: NIHSS 8. "
            "Right upper extremity 2/5 strength, right lower extremity 4/5. Left side "
            "5/5 throughout. Sensation grossly decreased on the right. No neglect. "
            "Cerebellar testing within normal limits on the left."
        ),
        "ed_workup": (
            "STAT non-contrast head CT shows no acute hemorrhage. CT angiography of the "
            "head and neck reveals a left middle cerebral artery M2 occlusion. Glucose, "
            "platelets, INR within range for thrombolytic candidacy. Within the standard "
            "tPA window. Risks and benefits of tPA discussed with the patient and family."
        ),
        "consult_focus": (
            "Neurology Stroke Service was consulted emergently. Patient was within the "
            "thrombolytic window. tPA was administered after risk-benefit discussion. "
            "Mechanical thrombectomy was performed in interventional radiology. Patient "
            "was admitted to the neurological intensive care unit for close monitoring."
        ),
        "imaging_kind": "Non-contrast head CT and CT angiography",
        "imaging_read": (
            "Non-contrast head CT: No acute intracranial hemorrhage. Subtle loss of gray-"
            "white matter differentiation in the left MCA distribution. ASPECTS score 8. "
            "CT angiography: Left M2 segment occlusion of the middle cerebral artery. "
            "Patent vertebrobasilar and contralateral anterior circulation. IMPRESSION: "
            "Findings consistent with acute left MCA territory infarct with M2 occlusion, "
            "candidate for endovascular intervention."
        ),
        "plan_bullets": [
            "Administer IV alteplase (tPA) per stroke protocol.",
            "Activate interventional radiology for mechanical thrombectomy.",
            "Admit to neurological intensive care unit; q1h neuro checks x 24 hours.",
            "Strict blood pressure control with goal SBP < 180 mmHg post-tPA.",
            "Initiate anticoagulation for atrial fibrillation after 24-48 hour interval, "
            "pending stability and repeat imaging.",
            "Speech, occupational, and physical therapy consultations.",
        ],
        "discharge_meds_add": [
            "Apixaban 5 mg PO BID (initiated for atrial fibrillation)",
            "High-intensity statin",
            "Continue antihypertensives",
        ],
        "discharge_instructions": (
            "Patient and family extensively counseled on stroke prevention, including "
            "medication adherence, dietary modification, and recognition of stroke warning "
            "signs (BE FAST). Outpatient stroke clinic follow-up scheduled. Speech and "
            "occupational therapy continuing as outpatient. Driving restrictions discussed."
        ),
    },
    "E78.5": {
        "label": "Hyperlipidemia, newly identified",
        "cc": "elevated cholesterol on routine outpatient labs",
        "ed_hpi": (
            "The patient is a {age}-year-old {sw} presenting for further evaluation of "
            "dyslipidemia identified on routine outpatient lipid screening. The patient is "
            "asymptomatic and denies chest pain, dyspnea on exertion, claudication, or "
            "transient neurologic symptoms. There has been no syncope. The patient has a "
            "sedentary lifestyle and a diet described as heavy in red meat and processed "
            "foods. Family history is notable for early coronary artery disease in the "
            "patient's father, who suffered a myocardial infarction at age 52."
        ),
        "hp_hpi": (
            "Admission was elected for observation given inpatient capacity at the affiliated "
            "outpatient cardiology clinic. The patient otherwise has a relatively benign "
            "medical history. Counseling and lifestyle modification will be reinforced "
            "during this brief stay."
        ),
        "pmh": ["Essential hypertension"],
        "meds": ["Amlodipine 5 mg PO daily"],
        "exam": (
            "General: Well-appearing, no acute distress. HEENT: No xanthomas or arcus "
            "senilis. Cardiovascular: Regular rate and rhythm, no murmurs. Lungs: Clear "
            "bilaterally. Abdomen: Soft, non-tender. Extremities: No edema. Skin: No "
            "tendinous xanthomas. Neurologic: Grossly intact."
        ),
        "ed_workup": (
            "Repeat fasting lipid panel pending. EKG without acute ischemic changes. "
            "Hemoglobin A1c within range. Thyroid stimulating hormone normal."
        ),
        "consult_focus": "No specialty consult required at this time.",
        "imaging_kind": "EKG and chest X-ray",
        "imaging_read": (
            "EKG: Normal sinus rhythm at 72 bpm. No acute ST-T wave changes. Chest X-ray: "
            "No acute cardiopulmonary process. IMPRESSION: Unremarkable."
        ),
        "plan_bullets": [
            "Initiate high-intensity statin therapy with atorvastatin 40 mg PO nightly.",
            "Dietary consultation; emphasize Mediterranean-style diet.",
            "Lifestyle counseling, including aerobic exercise goal of 150 minutes weekly.",
            "Repeat lipid panel in 3 months to assess response.",
            "Continue antihypertensive regimen.",
            "Outpatient primary care follow-up in 4 weeks.",
        ],
        "discharge_meds_add": [
            "Atorvastatin 40 mg PO nightly (new)",
            "Continue amlodipine",
        ],
        "discharge_instructions": (
            "Patient educated on the role of statin therapy, expected benefits, and "
            "potential side effects including muscle aches. Reinforced lifestyle "
            "modifications. Provided with dietary handouts. Follow-up labs scheduled."
        ),
    },
}

DEFAULT_DX = {
    "label": "General medical evaluation",
    "cc": "general symptoms warranting inpatient observation",
    "ed_hpi": (
        "{age}-year-old {sw} presenting for evaluation of symptoms warranting inpatient "
        "observation. A detailed history is being obtained. Initial workup is in progress."
    ),
    "hp_hpi": "Further history pending collateral information.",
    "pmh": ["See prior outpatient records"],
    "meds": ["Reconciliation pending"],
    "exam": "Stable on examination without acute findings.",
    "ed_workup": "Routine labs and imaging pending.",
    "consult_focus": "No specialty consult required at this time.",
    "imaging_kind": "Routine imaging",
    "imaging_read": "No acute findings identified.",
    "plan_bullets": [
        "Admit for observation and supportive care.",
        "Routine labs in AM.",
        "Reassess clinical status every 24 hours.",
    ],
    "discharge_meds_add": ["Resume home medications"],
    "discharge_instructions": (
        "Routine return precautions discussed. Outpatient follow-up scheduled."
    ),
}

# =============================================================================
# Generic narrative chunks for daily progress / nursing notes
# =============================================================================

NURSING_DAY = [
    ("0700", "Received patient from off-going RN. Pt alert and oriented x3, resting in bed "
             "with HOB elevated 30 degrees. Skin warm and dry. IV site in left antecubital "
             "patent, no signs of infiltration. Pt denies acute complaints. Vitals stable "
             "and within parameters. Will continue to monitor."),
    ("0930", "Pt ambulated to bathroom with standby assist, tolerated well. Encouraged use "
             "of incentive spirometer 10x per hour while awake; pt verbalized understanding. "
             "Reviewed plan of care with pt, no questions at this time."),
    ("1115", "Pt tolerating PO intake well, breakfast tray 75% consumed. Bowel sounds active "
             "in all four quadrants. Pain assessed at 2/10, no analgesic required. Pt "
             "watching television, in no apparent distress."),
    ("1330", "Physician rounded with team at bedside. Plan of care reviewed and updated. "
             "Pt's questions addressed regarding anticipated length of stay. Family present "
             "and engaged in discussion."),
    ("1500", "Routine vitals taken and within ordered parameters. Pt resting comfortably. "
             "IV fluids running at ordered rate. Telemetry shows sinus rhythm without "
             "ectopy."),
    ("1700", "Dinner tray delivered, pt encouraged to ambulate prior to meal. Pt tolerated "
             "ambulation in hallway with steady gait and no complaints of dyspnea on "
             "exertion."),
    ("1900", "Handoff received from day shift. Pt status reviewed, no acute issues. Plan of "
             "care current. Continued monitoring per protocol."),
    ("2100", "PRN analgesic administered per pt request for pain rated 4/10. Pt verbalized "
             "good effect after 30 minutes, pain now 1/10. No adverse reaction noted."),
    ("2330", "Pt sleeping. Vitals quietly obtained without disturbing pt. All within "
             "parameters. Telemetry without significant events."),
    ("0330", "Pt awakened briefly for routine vital signs and medication administration. "
             "Returned to sleep without difficulty. Continues to deny pain or discomfort."),
]

PROGRESS_SUBJECTIVE = [
    "Patient reports feeling better overnight. Slept reasonably well.",
    "Patient endorses ongoing fatigue but improved appetite. Denies new complaints.",
    "Patient with subjective improvement in primary symptoms. Cooperative with care.",
    "Patient reports persistent but slowly improving symptoms. Tolerating oral intake.",
    "Family at bedside, engaged in care planning. Patient in good spirits.",
    "Patient reports interrupted sleep due to overnight monitoring; otherwise stable.",
]

PROGRESS_OBJECTIVE = [
    "Vital signs stable over the past 24 hours. Afebrile. Heart rate normal range.",
    "Vitals trending in the appropriate direction. Volume status reassessed and acceptable.",
    "Lungs clear with improved aeration compared to prior exam. No new murmurs.",
    "Abdomen soft and non-tender. Bowel function returning to normal.",
    "Skin intact without breakdown. No signs of infection at IV sites.",
    "Tolerating diet without nausea. Ambulating with reduced assistance.",
]

PROGRESS_ASSESSMENT_TAIL = [
    "Continuing to respond to current management strategy.",
    "Improvement appropriate for hospital day, plan for continued in-patient management.",
    "Stable with anticipated discharge in the coming days if trajectory continues.",
    "Will continue to monitor closely; no escalation of care required at this time.",
    "Slight improvement noted overall; will reassess in subsequent rounds.",
]

# =============================================================================
# Helpers
# =============================================================================

def sex_word(raw) -> str:
    if not isinstance(raw, str):
        return "patient"
    s = raw.strip().lower()
    if s.startswith("m"):
        return "male"
    if s.startswith("f"):
        return "female"
    return "patient"


def safe_str(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def is_missing(v) -> bool:
    if pd.isna(v):
        return True
    s = str(v).strip().lower()
    return s in {"", "na", "n/a", "null", "?", "-", "unknown", "still admitted"}


def parse_any_date(s: str):
    if is_missing(s):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def estimate_los(row) -> int:
    admit = parse_any_date(safe_str(row["admission_date"]))
    discharge = parse_any_date(safe_str(row["discharge_date"]))
    if admit and discharge:
        return max(1, (discharge - admit).days)
    los_raw = safe_str(row["length_of_stay_days"])
    try:
        return max(1, int(float(los_raw)))
    except ValueError:
        return random.randint(3, 8)


def inject_noise(text: str) -> str:
    """Sprinkle realistic abbreviation / typo noise to make corpus messy."""
    if random.random() < 0.30:
        text = text.replace("shortness of breath", "SOB")
    if random.random() < 0.25:
        text = text.replace("chest pain", "CP")
    if random.random() < 0.20:
        text = text.replace("nausea and vomiting", "N/V")
    if random.random() < 0.15:
        text = re.sub(r"\bthe\b", "teh", text, count=1)
    return text


# =============================================================================
# Text formatting helpers
# =============================================================================

def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(
        text,
        width=LINE_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def major_header(title: str) -> list[str]:
    bar = "=" * LINE_WIDTH
    return ["", bar, title.upper(), bar]


def section_header(title: str) -> list[str]:
    return ["", title, "-" * len(title)]


def note_header(title: str, author: str, role: str, when: datetime) -> list[str]:
    when_str = when.strftime("%Y-%m-%d %H:%M")
    out = major_header(title)
    out.append(f"Author:   {author}  ({role})")
    out.append(f"Recorded: {when_str}")
    out.append("")
    return out


def bullets(items, start: int = 1) -> list[str]:
    out = []
    for i, line in enumerate(items, start):
        wrapped = wrap(f"{i}. {line}", indent="")
        # textwrap won't preserve the leading "1. " indent for continuation lines;
        # fix by re-wrapping with subsequent indent
        wrapped = textwrap.fill(
            f"{i}. {line}",
            width=LINE_WIDTH,
            subsequent_indent="   ",
            break_long_words=False,
            break_on_hyphens=False,
        )
        out.append(wrapped)
    return out


# =============================================================================
# Per-note renderers — each returns a list of strings (lines)
# =============================================================================

def social_hx_block(row, rng) -> str:
    tobacco = safe_str(row["smoking_status"])
    if is_missing(tobacco):
        tobacco_line = "Tobacco: not documented at this encounter."
    else:
        tobacco_line = f"Tobacco: {tobacco}."
    alcohol = rng.choice(["denies", "occasional, < 2 drinks/week", "social use only", "prior heavy use, now in recovery"])
    drugs = rng.choice(["denies", "denies current use", "remote marijuana use"])
    lives = rng.choice(["alone", "with spouse", "with adult children", "independently in assisted living"])
    return f"{tobacco_line} Alcohol: {alcohol}. Illicit drugs: {drugs}. Lives {lives}."


def render_ed_triage(row, dx, when: datetime, rng) -> list[str]:
    rn = rng.choice(PROVIDERS["rn"])
    bp = safe_str(row["blood_pressure"]) or "138/82"
    out = note_header("Emergency Department - Triage Note", rn, "Triage RN", when)
    body = (
        f"Patient arrived to the emergency department via "
        f"{rng.choice(['private vehicle','EMS','walk-in'])} with chief complaint of {dx['cc']}. "
        f"Reported symptom onset is "
        f"{rng.choice(['less than 24 hours ago','approximately 2 days ago','several days ago','this morning'])}. "
        f"Initial vitals on triage: BP {bp}, HR {rng.randint(70,118)}, RR {rng.randint(14,22)}, "
        f"Temp {round(rng.uniform(97.4, 102.5), 1)} F, SpO2 {rng.randint(89, 99)}% on room air. "
        f"Pain rated {rng.randint(0,9)}/10. Patient is alert and oriented x3, no acute distress observed at triage. "
        f"Acuity assigned: ESI level {rng.randint(2,3)}. Patient placed in room {rng.randint(1,24)}, "
        f"ED physician notified."
    )
    out.append(wrap(inject_noise(body)))
    return out


def render_ed_md(row, dx, when: datetime, rng) -> list[str]:
    md, role = rng.choice(PROVIDERS["ed_md"])
    sw = sex_word(safe_str(row["sex"]))
    age = safe_str(row["age"])
    out = note_header("Emergency Department - Physician Evaluation", md, role, when)

    out += section_header("Chief Complaint")
    out.append(wrap(dx["cc"].capitalize() + "."))

    out += section_header("History of Present Illness")
    out.append(wrap(inject_noise(dx["ed_hpi"].format(age=age, sw=sw))))

    out += section_header("Review of Systems")
    out.append(wrap(
        "Constitutional, cardiovascular, respiratory, gastrointestinal, genitourinary, "
        "musculoskeletal, neurologic, integumentary, hematologic, and psychiatric systems "
        "were reviewed. Pertinent positives and negatives are documented within the HPI. "
        "All other systems negative or non-contributory as obtained."
    ))

    out += section_header("Past Medical History")
    out.append(wrap("; ".join(dx["pmh"]) + "."))

    out += section_header("Home Medications")
    out.append(wrap("; ".join(dx["meds"]) + "."))

    out += section_header("Allergies")
    out.append(wrap(rng.choice([
        "No known drug allergies.",
        "Penicillin (hives, per patient).",
        "Sulfa antibiotics (rash).",
        "NKDA. No food or environmental allergies reported.",
    ])))

    out += section_header("Social History")
    out.append(wrap(social_hx_block(row, rng)))

    out += section_header("Physical Examination")
    out.append(wrap(dx["exam"]))

    out += section_header("ED Workup")
    out.append(wrap(dx["ed_workup"]))

    out += section_header("Medical Decision Making")
    out.append(wrap(
        f"This is a {age}-year-old {sw} presenting with {dx['cc']}. The differential "
        f"considered includes the primary diagnosis as well as alternatives that have been "
        f"reasonably excluded by the workup detailed above. The patient's presentation, "
        f"physical examination, and initial diagnostic studies are most consistent with "
        f"{dx['label']}. Given clinical severity and the need for further inpatient "
        f"management, the patient will be admitted to the medicine service. Admitting "
        f"hospitalist contacted and accepts care. Risk/benefits of admission and proposed "
        f"workup discussed with the patient, who verbalizes understanding and agrees with "
        f"the plan."
    ))
    return out


def render_hp(row, dx, when: datetime, rng) -> list[str]:
    md, role = rng.choice(PROVIDERS["hospitalist"])
    sw = sex_word(safe_str(row["sex"]))
    age = safe_str(row["age"])
    out = note_header("History & Physical - Admission Note", md, role, when)

    out += section_header("Identification & Source")
    out.append(wrap(
        f"Patient is a {age}-year-old {sw}. History obtained from the patient "
        f"{rng.choice(['and accompanying family member', 'directly, who is a reliable historian', 'with assistance of interpreter services'])}. "
        f"Records from prior encounters at this institution were reviewed."
    ))

    out += section_header("Chief Complaint")
    out.append(wrap(dx["cc"].capitalize() + "."))

    out += section_header("History of Present Illness")
    out.append(wrap(inject_noise(dx["ed_hpi"].format(age=age, sw=sw))))
    out.append("")
    out.append(wrap(dx["hp_hpi"]))

    out += section_header("Past Medical History")
    out.append(wrap("; ".join(dx["pmh"]) + "."))

    out += section_header("Past Surgical History")
    out.append(wrap(rng.choice([
        "Appendectomy in childhood; otherwise none.",
        "Cholecystectomy 2015. Tonsillectomy in childhood.",
        "No prior surgical interventions.",
        "Coronary artery bypass grafting x 3, 2018.",
        "Total knee arthroplasty (right), 2020.",
    ])))

    out += section_header("Family History")
    out.append(wrap(
        "Family history reviewed in detail and is significant for the conditions noted "
        "in the HPI. No known hereditary syndromes. No bleeding disorders identified."
    ))

    out += section_header("Social History")
    out.append(wrap(social_hx_block(row, rng)))
    out.append("")
    out.append(wrap(
        f"Marital status: {rng.choice(['married','single','widowed','divorced'])}. "
        f"Occupation: {rng.choice(['retired','clerical','retail','construction','healthcare worker','homemaker'])}. "
        f"Functional status at baseline: independent in ADLs."
    ))

    out += section_header("Home Medications & Allergies")
    out.append(wrap("Medications: " + "; ".join(dx["meds"]) + "."))
    out.append(wrap("Allergies: per ED documentation; reconfirmed with patient on admission."))

    out += section_header("Review of Systems")
    out.append(wrap(
        "10-point review of systems performed and negative aside from items documented "
        "in the HPI. Specifically denies recent unintentional weight changes, night sweats, "
        "easy bruising or bleeding, new rashes, joint swelling, or psychiatric symptoms."
    ))

    out += section_header("Physical Examination")
    out.append(wrap(dx["exam"]))

    out += section_header("Diagnostic Studies")
    out.append(wrap(dx["ed_workup"]))

    out += section_header("Assessment & Plan")
    out.append(wrap(
        f"Primary diagnosis: {dx['label']}. The patient will be admitted to the medicine "
        f"service. The active issues and corresponding management plan are as follows:"
    ))
    out.append("")
    out += bullets(dx["plan_bullets"])
    out.append("")
    out.append(wrap(
        "DVT prophylaxis: mechanical and/or pharmacologic per institutional protocol. "
        "Code status: full code, confirmed with the patient. Disposition: anticipated "
        "discharge home with primary care follow-up once clinically stable."
    ))
    return out


def render_progress_note(row, dx, when: datetime, hospital_day: int, rng) -> list[str]:
    pool = PROVIDERS["hospitalist"] + PROVIDERS["midlevel"]
    md, role = rng.choice(pool)
    out = note_header(f"Progress Note - Hospital Day {hospital_day}", md, role, when)

    bp = safe_str(row["blood_pressure"]) or "128/78"
    vitals_line = (
        f"Vitals (last 24h): BP {bp}, HR {rng.randint(62,98)}, RR {rng.randint(12,20)}, "
        f"Temp {round(rng.uniform(97.0, 100.4),1)} F, "
        f"SpO2 {rng.randint(92,99)}% on {rng.choice(['room air','2L NC','3L NC'])}. "
        f"I/Os: in {rng.randint(800,2200)} mL / out {rng.randint(700,2400)} mL."
    )
    assessment = f"{dx['label']}. Hospital day {hospital_day}. {rng.choice(PROGRESS_ASSESSMENT_TAIL)}"

    out += section_header("S - Subjective")
    out.append(wrap(rng.choice(PROGRESS_SUBJECTIVE)))

    out += section_header("O - Objective")
    out.append(wrap(vitals_line))
    out.append("")
    out.append(wrap(rng.choice(PROGRESS_OBJECTIVE)))

    out += section_header("A - Assessment")
    out.append(wrap(assessment))

    out += section_header("P - Plan")
    out += bullets(dx["plan_bullets"][:4])
    out.append("")
    out.append(wrap(
        f"Will reassess in the morning. Discharge planning ongoing; anticipated discharge "
        f"in {rng.choice(['1','1-2','2-3'])} days if clinical trajectory continues."
    ))
    return out


def render_nursing_note(row, when: datetime, rng) -> list[str]:
    rn = rng.choice(PROVIDERS["rn"])
    out = note_header("Nursing Note", rn, "Registered Nurse", when)
    selected = rng.sample(NURSING_DAY, k=rng.randint(3, 5))
    selected.sort(key=lambda t: t[0])
    for ts, text in selected:
        out.append(wrap(f"{ts} - {text}", indent=""))
        # ensure continuation lines align (use indent for subsequent)
        # re-wrap with hanging indent for readability
        out[-1] = textwrap.fill(
            f"{ts} - {text}",
            width=LINE_WIDTH,
            subsequent_indent="       ",
            break_long_words=False,
            break_on_hyphens=False,
        )
        out.append("")
    return out


def render_consult(row, dx, when: datetime, rng) -> list[str]:
    specialty, attending = CONSULT_SPECIALTY.get(safe_str(row["primary_diagnosis_code"]), (None, None))
    if not specialty:
        return []
    out = note_header(f"{specialty} Consultation", attending or "Consulting Attending, MD", specialty, when)

    out += section_header("Reason for Consult")
    out.append(wrap(f"Evaluation and management recommendations for the active issue of {dx['label']}."))

    out += section_header("History")
    out.append(wrap(
        "Reviewed history as documented by the admitting team. Spoke with the patient at "
        "the bedside. Examined the patient. Reviewed laboratory and imaging data."
    ))

    out += section_header("Impression")
    out.append(wrap(dx["consult_focus"]))

    out += section_header("Recommendations")
    out += bullets(dx["plan_bullets"])
    out.append("")
    out.append(wrap(
        "Thank you for this interesting consultation. Will continue to follow during this "
        "admission. Please do not hesitate to contact the consulting team with any questions "
        "or changes in clinical status."
    ))
    return out


def render_imaging(row, dx, when: datetime, rng) -> list[str]:
    rad, role = rng.choice(PROVIDERS["rad"])
    out = note_header(f"Radiology Report - {dx['imaging_kind']}", rad, role, when)

    out += section_header("Clinical Indication")
    out.append(wrap(dx["cc"].capitalize() + "."))

    out += section_header("Technique")
    out.append(wrap(
        "Standard departmental protocol was utilized. Images were reviewed on a PACS "
        "workstation. Comparison made to prior studies where available."
    ))

    out += section_header("Findings")
    out.append(wrap(dx["imaging_read"]))
    return out


def render_pharmacy(row, dx, when: datetime, rng) -> list[str]:
    pharm, role = rng.choice(PROVIDERS["pharm"])
    out = note_header("Pharmacy - Medication Reconciliation", pharm, role, when)

    out += section_header("Medications Reviewed")
    out.append(wrap("Home medications reconciled with the patient and family at the bedside."))
    out.append("")
    out += bullets(dx["meds"])
    out.append("")
    out += section_header("Inpatient Recommendations")
    out.append(wrap(
        "Reviewed admission orders for appropriateness, drug-drug interactions, renal and "
        "hepatic dose adjustment, and therapeutic duplication. No critical interactions "
        "identified. Continued surveillance during this admission."
    ))
    out += section_header("Counseling")
    out.append(wrap(
        "Pharmacy will provide structured discharge counseling on any new medications "
        "and adherence strategies prior to discharge."
    ))
    return out


def render_discharge(row, dx, when: datetime, rng) -> list[str]:
    md, role = rng.choice(PROVIDERS["hospitalist"])
    out = note_header("Discharge Summary", md, role, when)

    out += section_header("Admission Diagnosis")
    out.append(wrap(dx["label"] + "."))

    out += section_header("Discharge Diagnosis")
    out.append(wrap(dx["label"] + " - improved with treatment."))

    out += section_header("Hospital Course")
    out.append(wrap(
        f"The patient was admitted with {dx['cc']}. Initial workup, as detailed in the "
        f"admission note and emergency department documentation, was consistent with "
        f"{dx['label']}. Treatment was initiated as outlined in the plan, with appropriate "
        f"specialty consultation. Over the course of the admission, the patient demonstrated "
        f"clinical improvement, with normalization of pertinent laboratory and physical "
        f"examination findings. The patient remained hemodynamically stable throughout the "
        f"stay. There were no complications related to the inpatient course. By the time of "
        f"discharge, the patient was tolerating an oral diet, ambulating without assistance, "
        f"voiding without difficulty, and medically stable for discharge home."
    ))

    out += section_header("Discharge Medications")
    out += bullets(dx["meds"] + dx["discharge_meds_add"])

    out += section_header("Discharge Condition")
    out.append(wrap("Stable. Ambulating. Tolerating diet. Pain controlled on oral analgesia."))

    out += section_header("Activity")
    out.append(wrap("Resume usual activities as tolerated unless otherwise specified."))

    out += section_header("Diet")
    out.append(wrap(rng.choice([
        "Regular diet.", "Cardiac diet (low sodium).", "Diabetic diet.",
        "Renal diet (low potassium, low phosphorus).",
    ])))

    out += section_header("Follow-up")
    out.append(wrap(
        "Primary care within 7-10 days. Specialty follow-up as outlined in the patient's "
        "after-visit summary. Outstanding laboratory results will be reviewed and "
        "communicated by the primary care provider."
    ))

    out += section_header("Discharge Instructions")
    out.append(wrap(dx["discharge_instructions"]))
    out.append("")
    out.append(wrap(
        "The patient verbalized understanding of all discharge instructions and was "
        "provided with written materials. Questions were answered to the patient's "
        "satisfaction."
    ))
    return out


# =============================================================================
# Per-patient orchestration
# =============================================================================

def build_chart(row, out_path: Path) -> None:
    icd = safe_str(row["primary_diagnosis_code"])
    dx = DX.get(icd, DEFAULT_DX)
    los = min(estimate_los(row), 12)

    # Deterministic RNG per patient so charts are reproducible
    rng = random.Random(f"chart-{row['patient_id']}")

    admit_date = parse_any_date(safe_str(row["admission_date"])) or datetime.now().date()
    admit_dt = datetime.combine(admit_date, datetime.min.time()).replace(hour=rng.randint(2, 22))

    hospital = rng.choice(HOSPITALS)
    weight_disp = (
        f"{safe_str(row['weight'])} {safe_str(row['weight_unit_hint'])}"
        if safe_str(row["weight"]) else "-"
    )

    lines: list[str] = []
    bar = "=" * LINE_WIDTH

    # Cover / face-sheet -----------------------------------------------------
    lines.append(bar)
    lines.append(hospital.upper().center(LINE_WIDTH))
    lines.append("PATIENT CHART - ENCOUNTER DOCUMENTATION".center(LINE_WIDTH))
    lines.append(bar)
    lines.append("")
    face_rows = [
        ("Patient ID",     safe_str(row["patient_id"])),
        ("Age",            safe_str(row["age"])),
        ("Sex",            safe_str(row["sex"])),
        ("Race",           safe_str(row["race"]) or "-"),
        ("Insurance",      safe_str(row["insurance"]) or "-"),
        ("Height",         f"{safe_str(row['height_cm'])} cm"),
        ("Weight",         weight_disp),
        ("Admit date",     safe_str(row["admission_date"])),
        ("Discharge date", safe_str(row["discharge_date"]) or "-"),
        ("Length of stay (est.)", f"{los} days"),
        ("Primary Dx",     safe_str(row["primary_diagnosis_code"])),
        ("Description",    safe_str(row["primary_diagnosis_desc"]) or "-"),
        ("Smoking status (CSV)", safe_str(row["smoking_status"]) or "-"),
    ]
    label_w = max(len(lbl) for lbl, _ in face_rows) + 2
    for lbl, val in face_rows:
        lines.append(f"{(lbl + ':').ljust(label_w)} {val}")
    lines.append("")
    lines.append(wrap(
        "The following sections contain the documentation generated during this admission, "
        "presented in chronological order. All content is synthetic and produced solely for "
        "educational purposes; any resemblance to real individuals is coincidental."
    ))
    lines.append("")

    # Notes ------------------------------------------------------------------
    cur = admit_dt
    lines += render_ed_triage(row, dx, cur, rng)

    cur += timedelta(minutes=rng.randint(20, 90))
    lines += render_ed_md(row, dx, cur, rng)

    cur += timedelta(hours=rng.randint(2, 5))
    lines += render_hp(row, dx, cur, rng)

    cur += timedelta(hours=rng.randint(2, 6))
    lines += render_pharmacy(row, dx, cur, rng)

    cur += timedelta(hours=rng.randint(1, 4))
    lines += render_imaging(row, dx, cur, rng)

    consult = render_consult(row, dx, cur + timedelta(hours=rng.randint(2, 6)), rng)
    if consult:
        lines += consult

    # Daily progress + nursing notes
    for day in range(1, los + 1):
        day_dt = admit_dt + timedelta(days=day - 1)
        for shift_hour in (8, 20):
            lines += render_nursing_note(row, day_dt.replace(hour=shift_hour, minute=rng.randint(0, 59)), rng)
        lines += render_progress_note(row, dx, day_dt.replace(hour=rng.randint(9, 12), minute=0), day, rng)

    # Discharge
    discharge_dt = admit_dt + timedelta(days=los, hours=rng.randint(8, 14))
    lines += render_discharge(row, dx, discharge_dt, rng)

    lines.append("")
    lines.append("-" * LINE_WIDTH)
    lines.append("End of encounter documentation. Synthetic data - not a real medical record.")
    lines.append("-" * LINE_WIDTH)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(f"Expected {CSV_PATH} - run generate_patients.py first.")
    df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, na_values=[])
    df = df.drop_duplicates(subset=["patient_id"]).reset_index(drop=True)

    OUT_DIR.mkdir(exist_ok=True)
    for i, row in df.iterrows():
        pid = row["patient_id"]
        build_chart(row, OUT_DIR / f"{pid}.txt")
        if (i + 1) % 100 == 0:
            print(f"  rendered {i + 1} / {len(df)} charts")

    print(f"Done. {len(df)} TXT charts written to {OUT_DIR}")


if __name__ == "__main__":
    main()
