"""Loading and parsing the NeuroAIHub dataset catalogue (one CSV per category, 22 metadata columns).

Shared by the Python package and the web app, so both read the data in exactly the same way.
"""
import re
from pathlib import Path

import pandas as pd

# CSVs bundled with the package (copied from web_app/assets/datasets by sync_data.py before a release).
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"
CATEGORY_ORDER = ["Neurodegenerative", "Neoplasm", "Cerebrovascular", "Psychiatric", "Spinal", "Neurodevelopmental", "Other"]

COLUMNS = [
    "dataset_name", "doi", "url", "year", "access_type", "institution", "country", "modality", "resolution",
    "subject_no", "slice_scan_no", "age_range", "acquisition_protocol", "format", "segmentation_mask",
    "preprocessing", "disease", "healthy_control", "staging_information", "clinical_data", "histopathology", "lab_data",
]

# Columns that get a "<col>_clean" companion (details in parentheses removed) for filtering, plotting and the agent.
CLEAN_COLUMNS = [
    "year", "access_type", "institution", "country", "modality", "resolution", "subject_no", "slice_scan_no",
    "age_range", "format", "disease", "segmentation_mask", "healthy_control", "staging_information",
    "clinical_data", "histopathology", "lab_data",
]
NUMERIC_COLUMNS = ["year", "subject_no", "slice_scan_no"]
MISSING = {"", "nan", "none", "not specified", "n/a"}

_INNER_PARENS = re.compile(r"\s*\([^()]*\)")
_LEADING_NUMBER = re.compile(r"^\s*[~≈>≥<≤]?\s*(\d+(?:\.\d+)?)")


def strip_details(text) -> str:
    """Remove every parenthesised detail, including nested ones: "MRI (T1w, FLAIR), PET (amyloid)" -> "MRI, PET"."""
    s = "" if text is None else str(text)
    prev = None
    while prev != s:
        prev, s = s, _INNER_PARENS.sub("", s)
    s = re.sub(r"[()]", "", s)  # stray unbalanced brackets
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([,;])\s*", r"\1 ", s)
    return s.strip(" ,;")


def split_terms(text) -> list:
    """Top-level terms of a multi-value cell, e.g. "MRI (DWI), CT; PET" -> ["MRI", "CT", "PET"]."""
    terms = []
    for part in re.split(r"[,;]", strip_details(text)):
        part = part.strip()
        if part.lower() not in MISSING and part not in terms:
            terms.append(part)
    return terms


def leading_number(text):
    m = _LEADING_NUMBER.match(str(text))
    return float(m.group(1)) if m else None


def yes_no(text) -> str:
    s = str(text).strip().lower()
    if s.startswith("yes"):
        return "yes"
    if s.startswith("no") and not s.startswith("not"):
        return "no"
    return "ns"


def load_database(csv_dir=None):
    """Read every category CSV. Returns (dataframes by category, combined DataFrame, category names).

    Categories follow CATEGORY_ORDER; other CSV files in the folder are added after them, alphabetically.
    """
    folder = Path(csv_dir) if csv_dir else PACKAGE_DATA_DIR
    files = {p.stem: p for p in folder.glob("*.csv")} if folder.exists() else {}
    if not files:
        raise FileNotFoundError(f"No database CSV files found in {folder}")
    categories = [c for c in CATEGORY_ORDER if c in files] + sorted(c for c in files if c not in CATEGORY_ORDER)
    dataframes = {}
    for category in categories:
        df = pd.read_csv(files[category], dtype=str, keep_default_na=False, encoding="utf-8-sig")
        df.columns = [str(c).strip() for c in df.columns]
        df = df.apply(lambda s: s.str.strip())
        df = df[(df != "").any(axis=1)]
        df = df.replace("", "Not specified")
        for col in CLEAN_COLUMNS:
            if col in df.columns:
                df[f"{col}_clean"] = df[col].map(strip_details)
        for col in NUMERIC_COLUMNS:
            if col in df.columns:
                df[f"{col}_clean"] = pd.to_numeric(df[col].map(leading_number), errors="coerce")
        dataframes[category] = df.assign(category=category)
    combined_df = pd.concat(dataframes.values(), ignore_index=True)
    return dataframes, combined_df, categories
