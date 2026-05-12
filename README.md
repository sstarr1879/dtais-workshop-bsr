# dtais-workshop-bsr

Workshop materials for generating and cleaning a small, deliberately-messy
synthetic dataset of de-identified inpatient encounters. Participants get a
structured CSV that needs cleaning and a corpus of long, multi-note clinical
text files that pair with it.

> **No real patient data.** Everything in this repo (and everything the scripts
> produce) is fully synthetic. Any resemblance to real individuals is coincidental.

## What's in the repo

```
synthetic_data/
├── generate_patients.py   # builds the structured CSV
└── generate_notes.py      # builds one long .txt chart per patient
```

Only code is committed. The generated CSV and notes are gitignored — each
participant runs the scripts locally to produce their own working copy.

## Quick start

```bash
pip install pandas numpy

cd synthetic_data
python generate_patients.py   # writes patients_raw.csv (1000 patients + 5 dupes)
python generate_notes.py      # writes patient_notes/PT00001.txt ... PT01000.txt
```

The notes generator reads `patients_raw.csv`, so run the patient generator
first. Both scripts are seeded (`SEED = 42`) and produce reproducible output.

## What the scripts produce

### `patients_raw.csv` (1005 rows, 18 columns)

One row per inpatient encounter. Columns include `patient_id`, `age`, `sex`,
`race`, `height_cm`, `weight`, `weight_unit_hint`, `admission_date`,
`discharge_date`, `length_of_stay_days`, `primary_diagnosis_code`,
`primary_diagnosis_desc`, `lab_test_name`, `lab_value`, `lab_unit`,
`blood_pressure`, `smoking_status`, `insurance`.

### `patient_notes/PT*.txt` (~1000 files)

One plain-text chart per patient containing a chronological set of notes for
the encounter:

- Face-sheet header
- ED triage note
- ED physician evaluation
- History & Physical admission note
- Pharmacy medication reconciliation
- Radiology report (modality matched to diagnosis)
- Specialty consult note (when warranted by the diagnosis)
- Two nursing shift notes per hospital day
- Daily SOAP progress note
- Discharge summary

Note content is diagnosis-aware: a sepsis chart gets a sepsis-specific HPI, an
ID consult, and a CT abd/pelvis read; a stroke chart gets a stroke HPI, NIHSS
exam, neurology consult, and CT/CTA read; etc. Vitals, BP, age, sex, dates,
diagnosis, and labs are pulled from the corresponding CSV row, so structured
and unstructured data are internally consistent.

## Workshop hooks — data quality issues seeded on purpose

The CSV is intentionally messy. Participants should expect to handle:

- **Date format inconsistency** — admit/discharge dates appear in five formats
  (`2024-01-15`, `01/15/2024`, `15-Jan-2024`, `01-15-2024`, `2024/01/15`).
- **Length-of-stay derivation** — three states per row: both dates present
  (LOS derivable), LOS pre-computed in `length_of_stay_days`, or discharge
  date missing entirely (encoded as `""`, `"NA"`, or `"still admitted"`).
- **Categorical inconsistency** — `sex` (`M` / `Male` / `male` / ` F`), `race`
  (`African American` / `AA` / `African-American`), `insurance`, and
  `smoking_status` all use inconsistent encodings.
- **Lab-test coding inconsistency** — the same canonical test appears under
  multiple labels (`HbA1c` / `A1C` / `Hemoglobin A1c` / `hba1c` / `HGBA1C` /
  `Glycated Hemoglobin`). Participants must consolidate before analysis.
- **Mixed units** — weight is sometimes in kg, sometimes in lbs (with a
  not-always-reliable `weight_unit_hint`); glucose/creatinine/LDL sometimes
  appear in non-canonical units (mmol/L, µmol/L).
- **Blood pressure format** — mostly `120/80`, occasionally `120 over 80`.
- **Heterogeneous missing-value tokens** — `""`, `NA`, `N/A`, `?`, `-`,
  `unknown`, `null`, mixed throughout.
- **Outliers** — ~0.5% of rows have absurd ages (`-2`, `200`, `999`).
- **Whitespace / case noise** — stray spaces and inconsistent capitalization
  in string fields.
- **Exact duplicates** — five rows are duplicated for dedup practice.

## Adjusting the data

Common knobs at the top of each script:

- `N_PATIENTS` in `generate_patients.py` (default `1000`).
- `SEED` in both scripts (default `42`) — change for a different reproducible
  sample.
- `LINE_WIDTH` in `generate_notes.py` (default `88`) — text wrap width.

The note generator caps per-chart length-of-stay at 12 days when building the
progress/nursing timeline so charts don't grow unbounded for long stays. Bump
the cap in `build_chart()` if longer charts are needed.
