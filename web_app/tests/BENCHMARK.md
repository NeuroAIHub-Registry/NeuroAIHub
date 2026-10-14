# NeuroAI chat agent — test questions and results

Database: `web_app/assets/datasets/*.csv` (368 datasets). Expected answers below were computed directly
from that file; they change if the database changes (the script `agent_benchmark.py` always recomputes them).

## How to run

Automatic (from `web_app`; several keys can be comma-separated in `OPENROUTER_API_KEYS`):

```
set OPENROUTER_API_KEY=sk-or-...
set BENCH_CHARTS=charts_out
python tests/agent_benchmark.py <model id> [question numbers, e.g. 1,2,10]
```

Manual: open the app, set Base URL `https://openrouter.ai/api/v1`, the model id and your key, and ask the questions
below **in this order in one chat** (Q4 is a follow-up to Q3). Each question costs ~2 requests; OpenRouter's free tier
allows 50 requests per day per key.

## Questions and expected answers

| # | Question | Expected answer (pass criteria) |
|---|---|---|
| 1 | How many datasets are in the Spinal category? | **41** |
| 2 | Find open-access glioma MRI datasets with segmentation masks published since 2020. | **16** matches; listed names must be real (e.g. BRISC, IMAGO, UTSW-Glioma, BraTS 2025) |
| 3 | Which Alzheimer's disease datasets include both MRI and PET? | **22** |
| 4 | Which of those are open access? *(follow-up to Q3)* | **6** (e.g. AMYPAD PNHS, OASIS-3) |
| 5 | Summarize the Cerebrovascular category. | **48** datasets, 2015–2026, Open 40 / Restricted 8, 37 with masks, top disease Stroke (20) |
| 6 | Plot the number of datasets published per year. | A line/bar chart 2000–2026; peak **2024 (38)** |
| 7 | I want to build a stroke lesion segmentation model on MRI. Which datasets do you recommend? | Only real datasets with masks, e.g. ATLAS v2.0, ISLES 2022/2024, ARC, CCNRP chronic lesion set; no invented names |
| 8 | Tell me about the ADNI dataset: access type, number of subjects and DOI. | **Restricted**; ~2,500 participants; DOI **10.1002/jmri.21049** (+ 10.1016/j.jalz.2011.09.172, 10.1002/alz.14321) |
| 9 | Do you have any retinal OCT datasets? | **None**; must not name or suggest datasets that are not in the database |
| 10 | Make a pie chart of open vs restricted access datasets in the Neoplasm category. | Pie chart; **60 Open / 19 Restricted** (79) |
| 11 | Show a bar chart of the 10 most common diseases in the database. | Bar chart; Glioma 44, Alzheimer's Disease 39, Stroke 20, Glioblastoma 17, Schizophrenia 16, … ("Healthy" cohorts are not a disease) |
| 12 | Compare the number of datasets in each category with a chart. | Chart; Neoplasm 79, Neurodegenerative 78, Psychiatric 49, Cerebrovascular 48, Spinal 41, Other 40, Neurodevelopmental 33 |
| 13 | Plot the number of MRI and CT datasets per year in the Cerebrovascular category, as two lines on one chart. | **Two** lines (MRI, CT); totals with known year MRI 31, CT 22; both peak in 2024 (7 and 5) |
| 14 | Create a scatter plot of publication year versus number of subjects for open-access datasets. | Scatter of **real** data: 279 open datasets, 254 plotted (25 have no subject count); no simulated points |
| 15 | Show a line chart of Alzheimer's disease datasets per year since 2015. | Line chart; **20** datasets since 2015, peak 2020 (4) |

What to look for beyond the numbers: every dataset name must exist in the database (the "How this answer was found"
panel in the app shows the lookups), charts must come from the data, and the model should not add filters you did not
ask for.

## Models tested (OpenRouter free tier, 14 Oct 2026)

| Model id | Result |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | **15/15** on the checks (Q1–9, Q10–15). Recommended. 5–36 s per answer. Its Q13/Q14 ran before the split-series and scatter tools existed: Q13 typed the counts into its own code (correct values) and Q14 plotted only 86 of 279 open datasets — both causes are fixed now (typed-in data is rejected; clean columns); re-run Q13–14 to confirm. |
| `cohere/north-mini-code:free` | **15/15 after fixes** (first run 14/15 with a simulated scatter plot, a combined instead of two-line chart and an invented dataset in Q9 — all three fixed in the agent and re-tested). Fast (5–20 s). |
| `dots-studio/dots-3-note-preview:free` | 3/8 on the first version; its failures (malformed arguments, XML tool calls, answering from memory, suggesting outside datasets) were fixed and Q2/Q9 re-tested OK. Slow (up to 90 s). |
| `liquid/lfm-2.5-2.6b:free` | 2/8 — too small: invents tools/values, text "charts", wrong counts. **Not recommended.** |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Q1 only (pass) — quota ran out. |
| `nvidia/nemotron-3.5-lightning:free` | Q1 only (pass). |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Q1 only (pass). |
| `openrouter/free` (router; picks a random free model) | Q1 only (pass); results will vary between calls. |
| `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free` | Not tested: rate-limited upstream all day. |
| `poolside/laguna-s-2.1:free`, `poolside/laguna-xs-2.1:free` | Not tested: rate-limited upstream. |
| `thinkingmachines/inkling:free`, `thinkingmachines/inkling-small:free` | Unusable via API (403 "only available on agentic harnesses"). |

Worth testing next: Gemma 4 31B, Nemotron 3 Ultra, Nemotron 3.5 Lightning, Laguna S (full Q1–15), and any paid
model you plan to recommend (e.g. a GPT or Claude model) as a reference.
