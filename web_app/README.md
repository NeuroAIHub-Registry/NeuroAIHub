# NeuroAIHub web app

A Streamlit app that serves the website (`site/index.html`) driven by the full
database, plus the existing NeuroAI chat agent underneath it.

## Run locally

```bash
cd web_app
pip install -r requirements.txt
streamlit run main.py
```

Run it from inside `web_app` so `.streamlit/config.toml` (theme) is picked up.

## How it fits together

| File | Role |
|---|---|
| `assets/datasets/*.csv` | The database: one CSV per category (file name = category, 22 columns). Edit these to update the site; new CSV files become new categories. |
| `data_utils.py` | Loads every category CSV (order in `CATEGORY_ORDER`); builds `<col>_clean` columns (parenthesised details removed, nested brackets handled) and the records sent to the website. `DATABASE_UPDATED` is the date shown on the page. |
| `site/index.html` | The website: browse, search, filters, cards, charts, CSV export. `__DATA__` and `__LOGO__` are filled in by `main.py`. |
| `main.py` | Renders the website, then the chat section (model connection + agent) and the footer. |
| `../package/neuroaihub/` | The chat agent (`agent.py`, `agent_tools.py`) and data parsing (`data.py`) live in the Python package; the app imports them from there, so the website and `pip install neuroaihub` run the same code. |
| `ui_utils.py` | Paginated result tables. |
| `dataset_submissions/` | "Submit a dataset" Google Form: script that creates it, setup notes, and a helper that turns responses into database rows (`SETUP.md`). |
| `usage_log.py`, `usage_logging/` | Anonymous usage logging to a private Google Sheet (setup: `usage_logging/SETUP.md`). |
| `tests/agent_benchmark.py`, `tests/BENCHMARK.md` | Checks the agent on 15 questions with known answers (needs an API key); questions and results. |

The website is rendered in an iframe that sizes itself to its content, so the page scrolls as one document; the "Chat"
links scroll the surrounding Streamlit page to the chat section.

## Chat agent

- The model only picks a tool and fills in structured filters; every count, name and link comes from the tools,
  computed from the database. A typical question costs 2 model calls (tool call + answer).
- Tools: `search_datasets` (all filters, follow-ups on the previous results, and hints about which filter to drop
  when nothing matches), `get_dataset_details`, `count_datasets` (with optional chart), `summarize_category`,
  `numeric_chart` (scatter/histogram/box plots of year and subject numbers) and `run_python` (last resort; sandboxed:
  only pandas/numpy/matplotlib/seaborn imports, no files or network, must compute from the real data).
- Robust to weaker/free models: repairs malformed arguments, reads tool calls written as JSON or XML text, retries
  rate-limit/5xx errors, strips `<think>` blocks, and nudges the model to use the tools if it answers from memory.
- Requires a model with tool (function) calling. Free option: OpenRouter key, base URL `https://openrouter.ai/api/v1`,
  model e.g. `nvidia/nemotron-3-super-120b-a12b:free`.

## Editing the database

Open a category CSV in any spreadsheet program or text editor and save it as CSV (UTF-8). Keep the header row and the
22 columns, and follow the conventions so filters and the chat agent read the values correctly:

- unknown values: `Not specified`; details go in parentheses after the main value, e.g. `MRI (T1w, FLAIR)`;
- `modality`: MRI, CT, PET, SPECT, X-ray, Ultrasound, DSA, Histology, Micro-CT, EEG, iEEG, MEG, Polysomnography
  (sub-types in parentheses: fMRI/DTI/MRA → `MRI (...)`, CTA → `CT (...)`);
- `access_type`: `Open` or `Restricted`, optionally with details, e.g. `Open (CC BY 4.0)`;
- yes/no columns (`segmentation_mask`, `healthy_control`, `staging_information`, `clinical_data`, `histopathology`,
  `lab_data`): start with `Yes`, `No` or `Not specified`;
- `format`: image formats only (NIFTI, DICOM, MetaImage, NRRD, Analyze, MINC, HDF5, PNG, JPG, TIFF, ...);
- `disease`: `Healthy` for healthy-volunteer datasets; `year` and `subject_no` start with a plain number.
Change `DATABASE_UPDATED` in `data_utils.py` when you update the data. Before publishing a new package version, run
`python package/sync_data.py` to copy the CSVs into the package.

## Deploying

On Streamlit Community Cloud the app's main file is `web_app/main.py`. Community Cloud reads `.streamlit/config.toml`
from the repository root, so the theme file exists in both places (the page styling does not depend on it; it only sets
the theme of native Streamlit widgets).
Optional usage logging: follow `usage_logging/SETUP.md`, then add `LOG_ENDPOINT` and `LOG_TOKEN` under the app's
Settings → Secrets. The keep-alive job is `.github/workflows/keep_alive.yml` in the repository root; add the new app's
URL to `APP_URLS` there if the app address changes.
