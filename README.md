# Dawai Saathi

A phone-call companion that helps seniors keep track of their daily medicines.
A caregiver enters and verifies the medicine schedule. The system reminds the senior,
records what the senior **reports**, and alerts the caregiver when help is needed.

This is a student hackathon prototype. It uses **fictional demo data only**.
It is a reminder and record-keeping tool. It does not verify that medicine was taken,
and it never gives medical advice.

**Current stage: Milestone 2 of 9 (caregiver dashboard).** A caregiver can add fictional elder
profiles, medicines and schedules in the browser, and they stay saved after the server restarts.
Nothing makes a call, sends a reminder or reads a prescription yet. Reminders, the rule engine,
the phone simulator and voice features come in later milestones.

## What you need

- Windows with **PowerShell**
- **Python 3.12** (tested version family; a newer Python is untested)
- Internet, only for the one-time `pip install`

Milestone 2 needs no account, no API key and no payment.

## First-time setup (PowerShell, from the project folder)

The project folder is the one that contains `requirements.txt`, `app` and `tests`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

If `Activate.ps1` is blocked ("running scripts is disabled on this system"), run this once
and answer `Y`, then repeat the activate line:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Already have Milestone 1 set up?

Copy the Milestone 2 files over your project, activate the environment and run
`pip install -r requirements.txt` once more. Milestone 2 adds one library, `python-multipart`:
without it the server cannot read what an HTML form sends. Your `data\dawai.db` keeps working:
Milestone 2 changes no table.

## Every time you open a new PowerShell window

Go to the project folder and activate the environment again. The prompt then starts with `(.venv)`.

```powershell
cd C:\path\to\dawai-saathi
.venv\Scripts\Activate.ps1
```

## Run the tests

```powershell
pytest
```

Expected last line: **`169 passed`** (the time differs).

What the tests do and do not cover:

- Every test gets its own throw-away database in memory, so tests never touch `data\dawai.db`.
- The tests use FastAPI's `TestClient` **without** its startup step. They do **not** run the
  app's startup code (the `lifespan` in `app/main.py`, which creates the real tables).
  A green `pytest` therefore does **not** prove that the real server starts.
- The "restart" test (`test_required_11_...`) closes one database connection and opens a new one
  on the same file. That is a close copy of a restart, not a real one.
- That is why the manual checks below are **mandatory**.

## Start the app

```powershell
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser (type `http://`, not `https://`).
Stop the server with **Ctrl + C**.

## Using the dashboard (a two-minute demo)

1. On the dashboard click **Add a new elder**. Enter a **fictional** name, "Dadaji" or "Aaji",
   a made-up number such as `+910000000001`, a language, a caregiver name, tick the consent box
   and press **Save elder**.
2. On the elder's page, under **Add a medicine**, enter a name, a spoken name such as
   `BP wali dawa`, and (optionally) the caregiver's own instruction. Press **Save medicine**.
3. Under **Add a schedule item**, choose the medicine, type a time such as `08:30`, leave the
   days ticked, and either:
   - tick "I have checked this schedule..." and type who checked it. It is saved as **Verified**
     with that name and the time you pressed Save; or
   - leave the box empty. It is saved as **UNVERIFIED** with no name and no time.
4. Go back to the dashboard. The totals and the elder list have changed.

## Mandatory completion check for Milestone 2 (do this by hand)

Milestone 2 is finished only when `pytest` passes **and** all of these are true:

1. `pytest` ends with `169 passed`.
2. `uvicorn app.main:app --reload` prints `Application startup complete.` and no error.
3. http://127.0.0.1:8000/health shows `{"status":"ok","database":"ok"}`.
4. The dashboard opens. Add one fictional elder, one medicine, one **verified** schedule and one
   **unverified** schedule (the demo above). The dashboard then shows 1 elder, 1 medicine,
   2 schedule items, "1 verified, 1 unverified".
5. The elder's page shows the verified item as **Verified by caregiver** with the name and an
   IST time, and the other item as **UNVERIFIED** (yellow row, "Will not be used for reminders").
6. Try a wrong time such as `25:30`. The page must show a red message and **Nothing was saved**.
   Also try `24:00`.
7. **Restart check.** Press **Ctrl + C** in the PowerShell window to stop the server, wait until the
   prompt returns, run `uvicorn app.main:app --reload` again and refresh the browser.
   The elder, medicine, both schedule items and the verification name and time must still be there.
8. After `git init` and `git add .`, `git status` does **not** list `.env`, `.venv` or `data/dawai.db`.

## Reset the demo database

`data\dawai.db` holds demo data only. To start again with an empty dashboard, stop the server
(Ctrl + C) and delete the file:

```powershell
Remove-Item data\dawai.db
```

The next start creates a fresh one. At startup the app creates tables that are missing, but it never
changes the rules of a table that already exists, so deleting the file is also the way to pick up a
changed table rule.

## What the database enforces, what the Milestone 2 forms enforce, and what later services must enforce

Do **not** assume a rule is already protected unless the table says so. "Database" rules hold even if
our code has a bug. "M2 form/service" rules hold for the dashboard pages only. Another program that
writes to the database file would skip them.

| Rule | Database | Milestone 2 forms/services | Who must enforce the rest |
| --- | --- | --- | --- |
| A row cannot point to a row that does not exist (foreign keys) | **Yes** (switched on in `app/db.py` for this app's connections) | - | - |
| Allowed values: language, occurrence status, call channel and outcome, report type and source, notification kind, channel and delivery status | **Yes** (CHECK rules) | Language is also checked by the form | - |
| A schedule time is `HH:MM` from 00:00 to 23:59 | **Yes** | **Yes**, refused with a message before saving | - |
| A schedule item marked "verified" has `verified_by` and `verified_at` filled in | **Yes** (may not be empty) | **Yes**: the name must not be blank, `verified_at` is the server clock, and an unverified item gets neither | - |
| A schedule item belongs to a medicine of the same elder | **No** (a foreign key only proves the medicine exists) | **Yes**: the form lists only this elder's medicines, and the service checks again | - |
| Consent is ticked before a profile is saved; the consent time is the server clock | **No** | **Yes** | - |
| Format of `repeat_days` (days 0 to 6) and of phone numbers (10 to 15 digits) | **No** | **Yes**, for the dashboard forms only | M3 service reads `repeat_days` defensively |
| One occurrence per schedule item per date | **Yes** (UNIQUE) | - | M3 service: create it only if missing |
| One attempt number per occurrence | **Yes** (UNIQUE) | - | - |
| Reports cannot be edited or deleted; a correction is a new row | **Yes** (two triggers; protects against mistakes in our code, not against someone editing the file with another tool) | - | M4: the correction feature |
| The same notification cannot be saved twice | **Yes**, if the same `dedupe_key` is used | - | M7: build the key the same way every time |
| Only **verified, active** schedule items create occurrences or calls | **No.** The database accepts an occurrence for an unverified item | The dashboard shows unverified items as UNVERIFIED but creates no reminders at all | **M3 reminder service** |
| At most two call attempts (first try plus one retry) | **No.** The database accepts attempt 3, 4, ... | - | **M3 reminder service** |
| A missed call never becomes a report or a "not taken" status | **No** | - | **M3 and M4 services** |
| A report matches its occurrence and call attempt; a correction points to a report of the same occurrence; the occurrence status follows the newest report | **No.** The database accepts an inconsistent report | - | **M4 report service** |
| A bare "haan" is never "taken"; confusion and help are checked first; a negation beats a positive | **No.** The rule engine does not exist yet | - | **M4 rule engine and its safety tests** |
| The inbound history feature only reads and never writes | **No** | - | **M6** (read-only code, with tests) |
| A notification says "delivered" only if it was delivered | **No.** Only the three allowed values are checked | - | **M7 notification service** |

"Verified" on a schedule means only that the caregiver says they checked it. The system does not
check it, and it never calls an elder's report "verified".

## Known limits of Milestone 2 (on purpose)

- An existing schedule item cannot be edited, deleted or verified later. To fix one, add a new item.
  (Edit and delete are not in the Milestone 2 list, and they need their own safety review.)
- Two identical schedule items are not detected as duplicates.
- There is no login. The dashboard is for running on one laptop with fictional data. Do not put it
  on the internet with real data.
- Times are typed as `HH:MM` and are Indian Standard Time. Times stored by the system (consent,
  verification) are kept in UTC and shown as IST.

## Folders

| Folder | What lives there |
| --- | --- |
| `app/` | The application code |
| `app/routes/` | Web addresses (pages and checks). Kept short. |
| `app/services/` | The logic: form checks and dashboard saving now; reminders, rule engine, speech and alerts later |
| `app/templates/` | HTML pages |
| `app/static/` | CSS (and later the phone simulator's JavaScript) |
| `data/` | The SQLite database file, created automatically (never uploaded to GitHub) |
| `tests/` | Automatic tests. Run them with `pytest`. |

## Secrets

Real keys go only in `.env`, which is listed in `.gitignore` and must never be uploaded
or pasted into a chat. `.env.example` shows the names of the settings with empty values.

## Common errors

| What you see | Fix |
| --- | --- |
| `python` is not recognized | Close and reopen PowerShell. If it still fails, install Python 3.12 and tick "Add python.exe to PATH". You can also try `py -m venv .venv` |
| `Activate.ps1 cannot be loaded ... running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y`, activate again |
| `ModuleNotFoundError: No module named 'fastapi'` (or `sqlalchemy`) | The environment is not active. Run `.venv\Scripts\Activate.ps1`, then `pip install -r requirements.txt` |
| The browser shows "Internal Server Error" after you press Save, and PowerShell shows `The python-multipart library must be installed to use form parsing` | You updated from Milestone 1 but did not install the new library. Activate the environment and run `pip install -r requirements.txt`, then start the server again |
| `ModuleNotFoundError: No module named 'app'` | You are not in the project folder. `cd` into the folder that contains `pytest.ini` |
| `uvicorn` is not recognized | Activate the environment, or run `python -m uvicorn app.main:app --reload` |
| The server will not start because the address is already in use (error 10048) | Use another port: `uvicorn app.main:app --reload --port 8001` and open `http://127.0.0.1:8001` |
| The browser cannot connect | The server window was closed, or the address starts with `https`. Start `uvicorn` again and use `http://127.0.0.1:8000` |
| The browser shows `{"detail":"Elder profile not found"}` after you typed an address like `/elders/7` | That elder does not exist (for example after deleting `data\dawai.db`). Go back to the dashboard |
| The page looks unstyled (plain text) | Press Ctrl + F5 to reload without the old stylesheet |
| `Remove-Item` cannot delete `data\dawai.db` because the file is in use | Stop the server first (Ctrl + C), close any database viewer, then delete the file |
