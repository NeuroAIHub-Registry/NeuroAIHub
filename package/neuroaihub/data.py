"""Loading and parsing the NeuroAIHub dataset catalogue (one CSV per category, 22 metadata columns).

Shared by the Python package and the web app, so both read the data in exactly the same way.

The package reads the latest database straight from the NeuroAIHub GitHub repository, so updating the CSVs on GitHub
updates every installation without a new package release. Downloads are cached for 24 hours; without internet the
cached copy, or else the copy bundled with the package, is used.
"""
import json
import os
import re
import shutil
import time
import urllib.request
import warnings
from pathlib import Path

import pandas as pd

# CSVs bundled with the package: offline fallback (copied from web_app/assets/datasets by sync_data.py at release time).
PACKAGE_DATA_DIR = Path(__file__).resolve().parent / "data"

# Live database on GitHub (override with the NEUROAIHUB_REPO / NEUROAIHUB_BRANCH environment variables).
GITHUB_REPO = os.environ.get("NEUROAIHUB_REPO", "NeuroAIHub-Registry/NeuroAIHub")
GITHUB_BRANCH = os.environ.get("NEUROAIHUB_BRANCH", "main")
GITHUB_DATA_PATH = "web_app/assets/datasets"
CACHE_DIR = Path(os.environ.get("NEUROAIHUB_CACHE", Path.home() / ".cache" / "neuroaihub"))
CACHE_HOURS = 24
last_source = ""   # where the most recent load_database() call read its data from
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


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "neuroaihub-python"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _download_from_github(timeout=20):
    """Download every category CSV from GitHub into the cache folder; returns that folder."""
    try:  # list the files, so new categories are picked up automatically
        listing = json.loads(_get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_DATA_PATH}"
                                  f"?ref={GITHUB_BRANCH}", timeout))
        names = [f["name"] for f in listing if f.get("name", "").endswith(".csv")]
    except Exception:  # e.g. the GitHub API rate limit: fall back to the known categories
        names = [c + ".csv" for c in CATEGORY_ORDER]
    if not names:
        raise RuntimeError("no CSV files listed on GitHub")
    target, tmp = CACHE_DIR / "datasets", CACHE_DIR / "datasets.downloading"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    raw = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_DATA_PATH}/"
    for name in names:
        content = _get(raw + urllib.request.quote(name), timeout)
        if b"dataset_name" not in content[:300]:
            raise RuntimeError(f"unexpected content for {name}")
        (tmp / name).write_bytes(content)
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    (CACHE_DIR / "fetched_at").write_text(str(time.time()))
    return target


def database_folder(source="auto", refresh=False):
    """Folder holding the database CSVs.

    source="auto": latest from GitHub (cached for CACHE_HOURS), falling back to the cache, then to the bundled copy.
    source="github": must come from GitHub (or a fresh cache). source="bundled": the copy shipped with the package.
    refresh=True: download now even if the cache is still fresh.
    """
    global last_source
    if source == "bundled":
        last_source = "bundled copy"
        return PACKAGE_DATA_DIR
    cached = CACHE_DIR / "datasets"
    try:
        age_hours = (time.time() - float((CACHE_DIR / "fetched_at").read_text())) / 3600
    except Exception:
        age_hours = None
    if not refresh and age_hours is not None and age_hours < CACHE_HOURS and any(cached.glob("*.csv")):
        last_source = f"GitHub ({GITHUB_REPO}, cached {age_hours:.1f} h ago)"
        return cached
    try:
        folder = _download_from_github()
        last_source = f"GitHub ({GITHUB_REPO}, downloaded now)"
        return folder
    except Exception as e:
        if source == "github":
            raise RuntimeError(f"Could not download the NeuroAIHub database from GitHub: {e}") from e
        if any(cached.glob("*.csv")):
            warnings.warn(f"Could not reach GitHub ({e}); using the cached NeuroAIHub database.")
            last_source = "cached copy (offline)"
            return cached
        warnings.warn(f"Could not reach GitHub ({e}); using the database bundled with the package, which may be older.")
        last_source = "bundled copy (offline)"
        return PACKAGE_DATA_DIR


def load_database(csv_dir=None, source="auto", refresh=False):
    """Read every category CSV. Returns (dataframes by category, combined DataFrame, category names).

    By default the latest database is read from GitHub (see database_folder); pass csv_dir to read a local folder.
    Categories follow CATEGORY_ORDER; other CSV files in the folder are added after them, alphabetically.
    """
    global last_source
    if csv_dir:
        folder = Path(csv_dir)
        last_source = str(folder)
    else:
        folder = database_folder(source, refresh)
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
