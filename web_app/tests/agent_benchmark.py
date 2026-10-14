"""Benchmark the NeuroAI chat agent on questions whose answers are computed from the database.

Usage (from web_app):
    set OPENROUTER_API_KEY=...            (PowerShell: $env:OPENROUTER_API_KEY="...")
    python tests/agent_benchmark.py nvidia/nemotron-3-super-120b-a12b:free [1,2,3]

Several keys can be given comma-separated in OPENROUTER_API_KEYS; the script moves to the next key when the current
one has fewer than 6 free requests left today. Optional: AGENT_BASE_URL (default https://openrouter.ai/api/v1),
BENCH_CHARTS=<folder> to save the charts for visual inspection.
Each question costs about 2 model calls (OpenRouter's free tier allows 50 requests per day per key).
Checks: expected numbers appear in the answer, a chart is produced with the right grouping/tool, and every dataset
named in bold exists in the database (hallucination check). Questions 1-9 are text questions, 10-15 are charts.
"""
import base64
import difflib
import json
import logging
import os
import re
import sys
import time
import urllib.request

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
os.chdir(APP)
sys.stdout.reconfigure(encoding="utf-8")
logging.disable(logging.WARNING)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
from data_utils import load_data  # noqa: E402  (also puts ../package on the path)
from neuroaihub.agent_tools import DatasetTools  # noqa: E402
from neuroaihub.agent import NeuroAIAgent  # noqa: E402

KEYS = [k.strip() for k in (os.environ.get("OPENROUTER_API_KEYS") or os.environ.get("OPENROUTER_API_KEY") or "").split(",") if k.strip()]
if not KEYS:
    sys.exit("Set OPENROUTER_API_KEY (or OPENROUTER_API_KEYS) first.")
CHARTS = os.environ.get("BENCH_CHARTS")


def free_left(key):
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
        return json.load(urllib.request.urlopen(req, timeout=20))["data"]["free_model_daily_requests"]["remaining"]
    except Exception:
        return 50  # not OpenRouter, or unknown
if len(sys.argv) < 2:
    sys.exit(__doc__)
model = sys.argv[1]
pick = set(map(int, sys.argv[2].split(","))) if len(sys.argv) > 2 else None

_, df, cats = load_data()
truth = DatasetTools(df, cats)
names = [n.lower() for n in df["dataset_name"]]
alz = truth._apply({"diseases": ["Alzheimer's Disease"], "modalities": ["MRI", "PET"], "modality_match": "all"})[0]
QUESTIONS = [
    (1, "How many datasets are in the Spinal category?", {"num": [len(df[df.category == "Spinal"])]}),
    (2, "Find open-access glioma MRI datasets with segmentation masks published since 2020.",
     {"num": [truth.search_datasets(diseases=["Glioma"], modalities=["MRI"], access="Open", segmentation_mask="yes", year_from=2020)["total_matches"]]}),
    (3, "Which Alzheimer's disease datasets include both MRI and PET?", {"num": [len(alz)]}),
    (4, "Which of those are open access?", {"num": [int((alz["_access"] == "Open").sum())], "followup": True}),
    (5, "Summarize the Cerebrovascular category.", {"num": [len(df[df.category == "Cerebrovascular"])]}),
    (6, "Plot the number of datasets published per year.", {"image": True}),
    (7, "I want to build a stroke lesion segmentation model on MRI. Which datasets do you recommend?", {"names": True}),
    (8, "Tell me about the ADNI dataset: access type, number of subjects and DOI.", {"contains": ["restricted", "10.1002/jmri.21049"]}),
    (9, "Do you have any retinal OCT datasets?", {"none": True}),
    # ---- visualization
    (10, "Make a pie chart of open vs restricted access datasets in the Neoplasm category.",
     {"image": True, "num": [int((truth.df[truth.df.category == "Neoplasm"]["_access"] == "Open").sum())],
      "tool": ("count_datasets", {"group_by": "access_type", "category": "Neoplasm"})}),
    (11, "Show a bar chart of the 10 most common diseases in the database.",
     {"image": True, "tool": ("count_datasets", {"group_by": "disease"})}),
    (12, "Compare the number of datasets in each category with a chart.",
     {"image": True, "num": [len(df[df.category == "Neoplasm"])], "tool": ("count_datasets", {"group_by": "category"})}),
    (13, "Plot the number of MRI and CT datasets per year in the Cerebrovascular category, as two lines on one chart.",
     {"image": True, "tool": ("count_datasets", {"split_by": "modality"})}),
    (14, "Create a scatter plot of publication year versus number of subjects for open-access datasets.",
     {"image": True, "tool": ("numeric_chart", {"chart": "scatter"})}),
    (15, "Show a line chart of Alzheimer's disease datasets per year since 2015.",
     {"image": True, "tool": ("count_datasets", {"group_by": "year"})}),
]

TOK = lambda s: set(re.findall(r"[a-z0-9]+", s.lower()))  # noqa: E731
SKIP = {c.lower() for c in cats} | {"open", "restricted", "yes", "no", "neuroradiology"}


def mentioned(text):
    out = []
    for b in re.findall(r"\*\*(.+?)\*\*", text):
        b = b.strip().strip(":").strip()
        if len(b) < 6 or re.match(r"[\d~≈>]", b) or b.lower() in SKIP:
            continue
        out.append(b)
    return out


def known(n):
    if re.search(r"(datasets?|recommend\w*|summary|matches|options?)", n, re.I) and not re.search(r"\d{4}", n):
        return True  # headings
    t = TOK(n.split(" (")[0]) or TOK(n)
    return any(t <= TOK(x) for x in names) or bool(difflib.get_close_matches(n.lower(), names, cutoff=0.8))


tools = DatasetTools(df, cats)
key_i = 0
history, log = [], []
for qid, q, chk in QUESTIONS:
    if pick and qid not in pick:
        continue
    while key_i < len(KEYS) and free_left(KEYS[key_i]) < 6:
        key_i += 1
    if key_i == len(KEYS):
        print("stopping: all keys are out of free requests for today")
        break
    agent = NeuroAIAgent(tools, KEYS[key_i], model, os.environ.get("AGENT_BASE_URL", "https://openrouter.ai/api/v1"))
    t = time.time()
    r = agent.ask(q, history)
    dt = time.time() - t
    text = r.text or r.error
    history += [{"role": "user", "content": q}, {"role": "assistant", "content": text}]
    nums = [int(x.replace(",", "")) for x in re.findall(r"\b\d[\d,]*\b", text)]
    ok, why = True, []
    for n in chk.get("num", []):
        if n not in nums:
            ok = False; why.append(f"expected {n}")
    if chk.get("image") and not r.images:
        ok = False; why.append("no chart")
    for s in chk.get("contains", []):
        if s not in text.lower():
            ok = False; why.append(f"missing '{s}'")
    if chk.get("followup") and not any(isinstance(a, dict) and a.get("within_previous_results") for _, a in r.steps):
        why.append("(did not use within_previous_results)")
    if chk.get("tool"):
        want_name, want_args = chk["tool"]
        if not any(n == want_name and all(str(a.get(k, "")).lower() == str(v).lower() for k, v in want_args.items())
                   for n, a in r.steps if isinstance(a, dict)):
            why.append(f"(expected {want_name} {want_args or ''})")
    if CHARTS and r.images:
        os.makedirs(CHARTS, exist_ok=True)
        stem = re.sub(r"\W+", "_", model)
        for i, img in enumerate(r.images):
            with open(os.path.join(CHARTS, f"{stem}_Q{qid}_{i}.png"), "wb") as fh:
                fh.write(base64.b64decode(img))
    bad = [m for m in mentioned(text) if not known(m)]
    if (chk.get("names") or chk.get("none")) and bad:
        ok = False; why.append(f"unknown names {bad}")
    if r.error:
        ok = False; why.append("ERROR " + r.error[:120])
    print(f"Q{qid} {'PASS' if ok else 'FAIL'} {dt:5.1f}s calls={r.model_calls} steps={r.steps} {' '.join(why)}")
    print("   ", text[:600].replace("\n", "\n    "))
    if r.error and r.model_calls == 0:
        print("stopping: model unavailable")
        break
    log.append(dict(ok=ok, calls=r.model_calls))
print("PASSED", sum(x["ok"] for x in log), "/", len(log), "| model calls", sum(x["calls"] for x in log))
