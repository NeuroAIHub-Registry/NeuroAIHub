import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# The chat agent and the data parsing live in the neuroaihub Python package (../package), so the website and
# `pip install neuroaihub` run exactly the same code.
_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "package"
if str(_PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_DIR))

from neuroaihub.data import (  # noqa: E402  (re-exported for the rest of the app)
    CATEGORY_ORDER, COLUMNS, load_database, split_terms, strip_details, yes_no,
)

# The database: one CSV per category (file name = category). Plain text, so every change shows up as a readable diff
# on GitHub. This is the copy to edit; package/sync_data.py copies it into the package before a release.
DB_DIR = Path(__file__).resolve().parent / "assets" / "datasets"
# Shown on the website; update together with the database files.
DATABASE_UPDATED = "October 2026"


@st.cache_resource
def load_data():
    try:
        return load_database(DB_DIR)
    except FileNotFoundError as e:
        st.error(f"❌ {e}", icon="⚠️")
        st.stop()


def site_records(combined_df: pd.DataFrame) -> list:
    """Compact records for the browser front end: raw metadata plus pre-parsed filter fields."""
    records = []
    for _, r in combined_df.iterrows():
        raw = {c: str(r.get(c, "Not specified")) for c in COLUMNS}
        year = r.get("year_clean")
        subjects = r.get("subject_no_clean")
        access_terms = split_terms(raw["access_type"])
        records.append({
            "c": r["category"],
            "f": raw,
            "yr": int(year) if pd.notna(year) else None,
            "n": float(subjects) if pd.notna(subjects) else None,
            "mods": split_terms(raw["modality"]),
            "dis": split_terms(raw["disease"]),
            "fmt": split_terms(raw["format"]),
            "ctry": split_terms(raw["country"]),
            "acc": access_terms[0] if access_terms else "Not specified",
            "mask": yes_no(raw["segmentation_mask"]),
            "hc": yes_no(raw["healthy_control"]),
        })
    return records
