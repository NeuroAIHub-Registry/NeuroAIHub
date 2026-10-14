# Usage logging — setup (about 10 minutes, free)

The app logs anonymously to a private Google Sheet. Logging stays **off** until steps 1–4 are done; the app works
the same without it.

What is stored: see the tables at the end. Never stored: API keys, the full base URL, IP addresses, browser/device
details, names, accounts, cookies.

## 1. Create the sheet
1. Go to <https://sheets.google.com> and create a blank spreadsheet, e.g. **NeuroAIHub usage log**.
   Keep it private (do not share it). The `chat` and `browse` tabs are created automatically on the first row.

## 2. Add the script
1. In the spreadsheet: **Extensions → Apps Script**.
2. Delete the example code and paste the whole content of [`apps_script.gs`](apps_script.gs).
3. On the line `const LOG_TOKEN = 'CHANGE-ME-to-a-long-random-text';` replace the text with your own long random
   string (e.g. 30+ letters and digits). Keep it secret — it protects the `chat` tab from fake rows.
4. Click **Save** (disk icon).

## 3. Publish it as a web app
1. **Deploy → New deployment** → gear icon → **Web app**.
2. Description: `NeuroAIHub log`. **Execute as: Me**. **Who has access: Anyone**.
   ("Anyone" only means the app and the website can send rows to it; nobody can read the sheet.)
3. Click **Deploy**, allow the permissions Google asks for (it needs to edit *this* spreadsheet).
4. Copy the **Web app URL** (it ends in `/exec`).

If you later change the script, use **Deploy → Manage deployments → edit (pencil) → Version: New version → Deploy**
so the URL stays the same.

## 4. Give the URL and token to the app
On <https://share.streamlit.io> → your app → **⋮ → Settings → Secrets**, paste:

```toml
LOG_ENDPOINT = "https://script.google.com/macros/s/XXXXXXXX/exec"
LOG_TOKEN = "the same long random text as in the script"
```

Save; the app restarts. For running locally, put the same two lines in `web_app/.streamlit/secrets.toml`
(this file is git-ignored — never commit it).

## 5. Check it works
1. Open the app, change a filter on the website, wait 3 seconds → a row appears in the `browse` tab.
2. Ask the chat agent a question → a row appears in the `chat` tab.
3. If nothing appears: check that the URL ends in `/exec`, that access is "Anyone", and that `LOG_TOKEN` is identical
   in the script and the secrets (only the `chat` tab needs the token).

## What is stored

**`chat`** (one row per question): `time_utc`, `session_id` (random, per visit), `turn`, `model`, `provider`
(host name only), `question` (full text), `answer` (first 2,000 characters), `lookups` (what the agent searched),
`datasets_returned`, `chart` (yes/no), `status` (ok / rate_limited / provider_error / failed / no_answer), `seconds`,
`model_calls`.

**`browse`** (website use; separate random session ID, not linked to the chat):
`time_utc`, `session_id`, `action`, `search_text`, `category`, `diseases`, `modalities`, `access`,
`segmentation_mask`, `healthy_control`, `year_from`, `year_to`, `sort`, `results`, `chart_settings`, `dataset`.
Actions: `filter` (one row after filters have been still for 3 s and changed since the last row), `category_tile`,
`download_csv`, `chart`, `opened_dataset` (full metadata opened), `opened_dataset_source` (source link clicked) —
the last two once per dataset per visit.

Limits: a Google Sheet holds 10 million cells (roughly a million chat rows); each cell holds up to 50,000 characters,
so questions longer than that (practically never) are cut there. Anyone could technically send fake `browse` rows to
the web-app URL (it is visible in the page); that only affects the log, never the dataset catalogue.
