# NeuroAIHub

Find public **neuroradiology datasets** by chatting with the NeuroAI Chat Agent — the same agent that powers the
[NeuroAIHub website](https://neuroai.streamlit.app) — over a curated database of 368 datasets in seven categories
(Neurodegenerative/Inflammatory Diseases, Neoplasm, Cerebrovascular Diseases, Psychiatric Diseases, Spine,
Neurodevelopmental Diseases, Other).

Paper: [AJNR, ajnr.A9363](https://www.ajnr.org/content/early/2026/04/24/ajnr.A9363) ·
Code: [GitHub](https://github.com/NeuroAIHub-Registry/NeuroAIHub)

## Install

```bash
pip install neuroaihub
```

## Chat with the database

```python
from neuroaihub import NeuroAIChatAgent

agent = NeuroAIChatAgent(
    api_key="YOUR_API_KEY",
    base_url="https://openrouter.ai/api/v1",          # leave out for OpenAI
    model="cohere/north-mini-code:free",               # e.g. "gpt-5" with OpenAI
)

result = agent.chat("Which open-access glioma MRI datasets have segmentation masks?")
agent.display(result)                  # answer, result table and charts (rich output in Jupyter)

result = agent.chat("Which of those were published since 2023?")   # follow-ups use the previous results
result["data"]                         # matching datasets as a pandas DataFrame
```

Any OpenAI-compatible provider works if the model supports tool (function) calling. Every dataset name, number and
link in an answer is computed from the database by the agent's tools — the model does not answer from memory.

`chat()` returns a dict: `text`, `data` (DataFrame or None), `image_b64` / `images` (charts as base64 PNG),
`steps` (database lookups made), `status`, `error`, `model_calls`. Use `agent.reset()` to start a new conversation and
`verbose=True` to print the lookups.

## Always the latest database

The package reads the database straight from the [NeuroAIHub GitHub repository](https://github.com/NeuroAIHub-Registry/NeuroAIHub/tree/main/web_app/assets/datasets),
so new and corrected datasets are available as soon as they are published there — no package update needed.
The download is cached for 24 hours (in `~/.cache/neuroaihub`); without internet the cached copy, or the copy bundled
with the package, is used. `NeuroAIChatAgent(..., refresh_data=True)` or `load_database(refresh=True)` forces a fresh
download; `agent.data_source` shows where the data came from.

## Use the database directly

```python
from neuroaihub import load_database

dataframes, combined_df, categories = load_database()   # latest from GitHub: one DataFrame per category + all combined
```

Each dataset has 22 metadata fields: name, DOI, URL, year, access type, institution, country, modality, resolution,
number of subjects and scans, age range, acquisition protocol, image format, segmentation masks, preprocessing,
disease, healthy controls, staging, clinical data, histopathology and lab data.

## Changes in 1.1.0

- New chat agent (identical to the website): tool calling instead of LangChain, about 2 model calls per question,
  charts (bar, pie, line, multi-series, scatter, histogram, box), follow-up questions, and robust handling of free
  and smaller models.
- Updated and cleaned database (368 datasets, seven categories), read live from GitHub.
- The dataset updating agent (`NeuroAIUpdater`) has been removed.

License: CC BY-NC-ND 4.0.
