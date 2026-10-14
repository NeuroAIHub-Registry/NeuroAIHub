"""Turn Google Form submissions into rows in the database format, ready for review.

1. In the responses sheet: File > Download > Comma-separated values (.csv).
2. From web_app:  python dataset_submissions/responses_to_csv.py "path/to/responses.csv"

Writes to dataset_submissions/pending/:
  <Category>.csv     new rows with the 22 database columns (unknown fields = "Not specified"); check and complete them,
                     then paste the rows into assets/datasets/<Category>.csv
  review_notes.csv   per submission: the free-text "Other details", the contributor's name/email (never copied into
                     the database), and possible duplicates already in the database
Submissions whose link or name is already in the database are reported and skipped.
"""
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP.parent / "package"))
from neuroaihub.data import COLUMNS, load_database  # noqa: E402

NS = "Not specified"
# form question title -> database column (titles as created by create_form.gs)
DIRECT = {
    "Dataset name": "dataset_name", "Link to the dataset": "url", "Disease / condition": "disease",
    "Imaging modality": "modality", "DOI": "doi", "Year released": "year", "Number of subjects": "subject_no",
    "Institution(s)": "institution", "Country / countries": "country", "Image file format": "format",
}
YES_NO = {"Segmentation masks / annotations included?": "segmentation_mask",
          "Healthy controls included?": "healthy_control", "Clinical data included?": "clinical_data"}


def _norm_url(u):
    return re.sub(r"^https?://(www\.)?", "", str(u).strip().lower()).rstrip("/")


def main(path):
    resp = pd.read_csv(path, dtype=str, keep_default_na=False)
    resp.columns = [c.strip() for c in resp.columns]
    missing = [t for t in ["Dataset name", "Link to the dataset", "Category"] if t not in resp.columns]
    if missing:
        sys.exit(f"Not a NeuroAIHub form export (missing columns: {missing})")

    _, db, _ = load_database(APP / "assets" / "datasets")
    known_urls = {_norm_url(u) for u in db["url"]}
    known_names = {n.strip().lower() for n in db["dataset_name"]}

    out_dir = HERE / "pending"
    out_dir.mkdir(exist_ok=True)
    rows, notes = {}, []
    for _, r in resp.iterrows():
        name = r.get("Dataset name", "").strip()
        if not name:
            continue
        duplicate = _norm_url(r.get("Link to the dataset", "")) in known_urls or name.lower() in known_names
        notes.append({
            "submitted": r.get("Timestamp", ""), "dataset_name": name, "category": r.get("Category", ""),
            "already_in_database": "yes" if duplicate else "no", "other_details": r.get("Other details", ""),
            "contributor_name": r.get("Your name (for acknowledgement)", ""),
            "contributor_email": r.get("Your email (if we may contact you)", ""),
        })
        if duplicate:
            print(f"skipped (already in database): {name}")
            continue
        row = {c: NS for c in COLUMNS}
        for title, col in DIRECT.items():
            value = str(r.get(title, "")).strip()
            if value:
                row[col] = value
        access = str(r.get("Access", "")).strip()
        row["access_type"] = "Open" if access.startswith("Open") else "Restricted" if access.startswith("Restricted") else NS
        for title, col in YES_NO.items():
            value = str(r.get(title, "")).strip()
            row[col] = value if value in ("Yes", "No") else NS
        category = str(r.get("Category", "")).strip()
        category = "Other" if not category or category.startswith("Other") else category
        rows.setdefault(category, []).append(row)

    for category, items in rows.items():
        target = out_dir / f"{category}.csv"
        new = pd.DataFrame(items, columns=COLUMNS)
        if target.exists():
            new = pd.concat([pd.read_csv(target, dtype=str, keep_default_na=False), new], ignore_index=True)
            new = new.drop_duplicates(subset=["dataset_name", "url"])
        new.to_csv(target, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"{len(items)} new row(s) -> {target}")
    pd.DataFrame(notes).to_csv(out_dir / "review_notes.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"review notes -> {out_dir / 'review_notes.csv'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
