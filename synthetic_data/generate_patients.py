"""Generate a synthetic, intentionally-messy de-identified patient dataset.

The output CSV is designed for a workshop on data cleaning: it contains
formatting inconsistencies, inconsistent coding of categorical values and
lab tests, mixed units, missing values, and fields that require derivation
or imputation (e.g. length of stay).

Run:
    python generate_patients.py
Produces:
    patients_raw.csv (1000 rows)
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

N_PATIENTS = 1000
SEED = 42
OUT_PATH = Path(__file__).parent / "patients_raw.csv"

rng = np.random.default_rng(SEED)
random.seed(SEED)


# ---------------------------------------------------------------------------
# Vocabularies — deliberately include synonyms / inconsistent casings so the
# workshop participants have to standardize them.
# ---------------------------------------------------------------------------

SEX_VARIANTS = ["M", "F", "Male", "Female", "male", "female", "m ", " F", "MALE", "FEMALE"]

RACE_VARIANTS = [
    "White", "white", "WHITE", "Caucasian",
    "Black", "black", "African American", "African-American", "AA",
    "Asian", "asian", "ASIAN",
    "Hispanic", "hispanic", "Latino", "Latina",
    "Native American", "AI/AN", "American Indian",
    "Other", "other", "Unknown", "unknown", "?",
]

# Same lab test, multiple encodings — participants need to consolidate.
LAB_TEST_VARIANTS = {
    "HbA1c": ["HbA1c", "Hemoglobin A1c", "A1C", "hba1c", "HGBA1C", "Glycated Hemoglobin"],
    "Glucose": ["Glucose", "GLU", "glucose", "Blood Glucose", "Serum Glucose", "BG"],
    "Creatinine": ["Creatinine", "CREAT", "creat", "Cr", "Serum Creatinine"],
    "LDL": ["LDL", "LDL-C", "LDL Cholesterol", "ldl", "Low-Density Lipoprotein"],
    "Sodium": ["Sodium", "Na", "NA", "sodium", "Serum Sodium"],
}

# Reasonable reference distributions per canonical test (mean, sd, unit).
LAB_DISTRIBUTIONS = {
    "HbA1c":      (6.5, 1.5, "%"),
    "Glucose":    (110, 35, "mg/dL"),
    "Creatinine": (1.0, 0.4, "mg/dL"),
    "LDL":        (115, 35, "mg/dL"),
    "Sodium":     (139, 3.5, "mmol/L"),
}

# Alternate units that get mixed in to force unit-standardization work.
ALT_UNITS = {
    "Glucose": ("mmol/L", lambda v: v / 18.0),       # mg/dL -> mmol/L
    "Creatinine": ("umol/L", lambda v: v * 88.4),    # mg/dL -> umol/L
    "LDL": ("mmol/L", lambda v: v / 38.67),
    # HbA1c and Sodium left in their canonical unit
}

ICD10_CODES = [
    ("E11.9", "Type 2 diabetes mellitus without complications"),
    ("I10",   "Essential (primary) hypertension"),
    ("J18.9", "Pneumonia, unspecified organism"),
    ("N17.9", "Acute kidney failure, unspecified"),
    ("I50.9", "Heart failure, unspecified"),
    ("J44.9", "Chronic obstructive pulmonary disease, unspecified"),
    ("A41.9", "Sepsis, unspecified organism"),
    ("K35.80","Unspecified acute appendicitis"),
    ("I63.9", "Cerebral infarction, unspecified"),
    ("E78.5", "Hyperlipidemia, unspecified"),
]

INSURANCE = ["Medicare", "Medicaid", "Private", "Self-Pay", "private", "MEDICARE", "Other"]

SMOKING_STATUS = ["Never", "Former", "Current", "never", "former", "current", "N", "Y", "unknown", ""]

MISSING_TOKENS = ["", "NA", "N/A", "n/a", "null", "NULL", "?", "-", "unknown", "Unknown"]


# ---------------------------------------------------------------------------
# Formatters that introduce realistic inconsistency
# ---------------------------------------------------------------------------

def format_date_messy(d: date) -> str:
    """Return the same date in one of several common formats."""
    fmt = random.choice([
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%m-%d-%Y",
        "%Y/%m/%d",
    ])
    return d.strftime(fmt)


def maybe_missing(value, p_missing: float = 0.05):
    """With probability p_missing, replace value with a random missing token."""
    if rng.random() < p_missing:
        return random.choice(MISSING_TOKENS)
    return value


def jitter_string(s: str, p: float = 0.10) -> str:
    """Occasionally add stray whitespace or change case."""
    if rng.random() < p:
        return f"  {s} "
    if rng.random() < p:
        return s.upper()
    if rng.random() < p:
        return s.lower()
    return s


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def build_patient(i: int) -> dict:
    pid = f"PT{i:05d}"

    # Demographics
    age = int(np.clip(rng.normal(58, 18), 0, 100))
    # Inject a few absurd outliers to be caught during cleaning
    if rng.random() < 0.005:
        age = random.choice([-2, 200, 999])

    sex = random.choice(SEX_VARIANTS)
    race = random.choice(RACE_VARIANTS)

    # Height (cm) and weight — weight unit varies (kg vs lbs) without being labeled
    height_cm = float(np.clip(rng.normal(170, 10), 140, 200))
    weight_kg = float(np.clip(rng.normal(80, 18), 35, 180))
    if rng.random() < 0.30:  # ~30% of rows reported in lbs without a unit column
        weight_value = round(weight_kg * 2.20462, 1)
        weight_unit_hint = "lbs"
    else:
        weight_value = round(weight_kg, 1)
        weight_unit_hint = "kg"

    # Admission / discharge — one of three states per row:
    #   1) both dates present (LOS derivable)
    #   2) only admit date + LOS_days populated
    #   3) discharge date missing entirely (still admitted / lost)
    admit = date(2024, 1, 1) + timedelta(days=int(rng.integers(0, 365)))
    los_true = int(np.clip(rng.exponential(5) + 1, 1, 60))
    discharge = admit + timedelta(days=los_true)

    state = rng.choice(["both", "los_only", "discharge_missing"], p=[0.65, 0.25, 0.10])
    if state == "both":
        admit_str = format_date_messy(admit)
        discharge_str = format_date_messy(discharge)
        los_days = ""  # left blank, must be derived
    elif state == "los_only":
        admit_str = format_date_messy(admit)
        discharge_str = ""
        los_days = los_true
    else:
        admit_str = format_date_messy(admit)
        discharge_str = random.choice(["", "NA", "N/A", "still admitted"])
        los_days = ""

    # Diagnosis
    icd, icd_desc = random.choice(ICD10_CODES)

    # One lab per patient (keeps the row schema simple). Pick a canonical test
    # then render it with one of its synonym labels and (sometimes) a
    # non-canonical unit.
    canonical_test = random.choice(list(LAB_TEST_VARIANTS.keys()))
    test_label = random.choice(LAB_TEST_VARIANTS[canonical_test])
    mean, sd, canon_unit = LAB_DISTRIBUTIONS[canonical_test]
    raw_value = float(np.clip(rng.normal(mean, sd), 0.1, mean + 6 * sd))

    if canonical_test in ALT_UNITS and rng.random() < 0.25:
        alt_unit, converter = ALT_UNITS[canonical_test]
        lab_value = round(converter(raw_value), 2)
        lab_unit = alt_unit
    else:
        lab_value = round(raw_value, 2)
        lab_unit = canon_unit

    # Vitals
    systolic = int(np.clip(rng.normal(130, 18), 80, 220))
    diastolic = int(np.clip(rng.normal(80, 12), 40, 130))
    bp = f"{systolic}/{diastolic}"
    if rng.random() < 0.05:  # alternate BP format
        bp = f"{systolic} over {diastolic}"

    insurance = random.choice(INSURANCE)
    smoking = random.choice(SMOKING_STATUS)

    row = {
        "patient_id": pid,
        "age": age,
        "sex": sex,
        "race": race,
        "height_cm": round(height_cm, 1),
        "weight": weight_value,  # NOTE: column is unitless — workshop hint
        "weight_unit_hint": weight_unit_hint,  # buried hint, not always reliable
        "admission_date": admit_str,
        "discharge_date": discharge_str,
        "length_of_stay_days": los_days,
        "primary_diagnosis_code": icd,
        "primary_diagnosis_desc": jitter_string(icd_desc),
        "lab_test_name": test_label,
        "lab_value": lab_value,
        "lab_unit": lab_unit,
        "blood_pressure": bp,
        "smoking_status": smoking,
        "insurance": insurance,
    }

    # Sprinkle missingness across selected columns
    for col, p in {
        "race": 0.06,
        "height_cm": 0.04,
        "weight": 0.03,
        "smoking_status": 0.10,
        "insurance": 0.05,
        "primary_diagnosis_desc": 0.03,
        "lab_unit": 0.04,
    }.items():
        row[col] = maybe_missing(row[col], p_missing=p)

    return row


def main() -> None:
    rows = [build_patient(i + 1) for i in range(N_PATIENTS)]
    df = pd.DataFrame(rows)

    # Inject a handful of exact duplicate rows so dedup is part of the exercise
    dup_idx = rng.choice(len(df), size=5, replace=False)
    df = pd.concat([df, df.iloc[dup_idx]], ignore_index=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
