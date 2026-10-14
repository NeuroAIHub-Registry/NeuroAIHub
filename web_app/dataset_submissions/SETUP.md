# "Submit a dataset" Google Form — setup (about 5 minutes, free)

The form is created by a script that you run **once in your own Google account (benyamingheiji@gmail.com)**, so the
form and its response sheet belong to you only. Nobody else gets edit access unless you add them.

## 1. Create the form
1. Sign in to Google as **benyamingheiji@gmail.com** (in a browser window where no other Google account is active, or
   check the account picture in the top-right corner in the next step).
2. Open <https://script.google.com> → **New project**.
3. Delete the example code and paste the whole content of [`create_form.gs`](create_form.gs). Save (disk icon).
4. In the toolbar choose the function **createSubmissionForm** and click **Run**.
5. Google asks for permission ("Google hasn't verified this app" → **Advanced → Go to project** → **Allow**). This only
   lets *your* script create a form and a spreadsheet in *your* Drive.
6. Open **Execution log** (bottom). It shows three links:
   - **PUBLIC FORM LINK** — the link people use to submit a dataset;
   - **Edit the form** — to change questions or wording later;
   - **Responses sheet** — where submissions arrive.
   The last line confirms the owner account. The script project can be deleted afterwards; the form stays.

## 2. Get an email for every submission (optional, recommended)
Open the form → **Responses** tab → **⋮** → **Get email notifications for new responses**.

## 3. Put the link on the website
In `web_app/main.py` set

```python
SUBMIT_FORM_URL = "https://docs.google.com/forms/d/e/.../viewform"
```

The website then shows a "Submit it in 2 minutes" button under the search results, a link in the "no datasets
match" message, and "Submit a dataset" in the footer. (Leave it empty to hide them.) Use the same link in the
README's "Community Contributions" section.

## The form

Required (6): dataset name · link to the dataset · category · disease/condition · imaging modality · access
(Open / Restricted / Not sure).

Optional: DOI · year released · number of subjects · institution(s) · country · image format · segmentation masks /
healthy controls / clinical data (Yes / No / Not sure) · other details (protocol, resolution, age range, ...) ·
the contributor's name (for acknowledgement) and email (for questions).

No Google sign-in is needed to submit, and respondents' emails are not collected automatically.

## Adding accepted submissions to the database
1. In the responses sheet: **File → Download → Comma-separated values (.csv)**.
2. From `web_app`:

   ```bash
   python dataset_submissions/responses_to_csv.py "C:/Users/.../Downloads/responses.csv"
   ```

3. `dataset_submissions/pending/` now has one CSV per category with the new rows in the database's 22-column format
   (unknown fields = "Not specified"), and `review_notes.csv` with each submission's free-text details, the
   contributor's name/email, and whether it is already in the database (those are skipped).
4. Check each row, complete what you can, then paste it into `assets/datasets/<Category>.csv`.

The `pending/` folder contains contributors' emails and is git-ignored — it is never committed.
