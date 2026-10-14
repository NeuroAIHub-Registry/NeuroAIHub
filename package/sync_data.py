"""Copy the dataset CSVs from the web app (the single place where the database is edited) into the package.

Run before building a release:  python sync_data.py
"""
import shutil
from pathlib import Path

here = Path(__file__).resolve().parent
src = here.parent / "web_app" / "assets" / "datasets"
dst = here / "neuroaihub" / "data"
dst.mkdir(exist_ok=True)
for old in dst.glob("*.csv"):
    old.unlink()
files = sorted(src.glob("*.csv"))
for f in files:
    shutil.copy2(f, dst / f.name)
print(f"Copied {len(files)} CSV files from {src} to {dst}")
