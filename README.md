# Dawai Saathi

A phone-call companion that helps seniors keep track of their daily medicines.
A caregiver enters and verifies the medicine schedule. The system reminds the senior,
records what the senior **reports**, and alerts the caregiver when help is needed.

This is a student hackathon prototype. It uses **fictional demo data only**.
It is a reminder and record-keeping tool. It does not verify that medicine was taken,
and it never gives medical advice.

**Current stage: Milestone 1 of 9 (foundation).** Only the server, the database and the
tests exist. The dashboard, reminders and voice features come in later milestones.

## What you need

- Windows with **PowerShell**
- **Python 3.12** (tested version family; a newer Python is untested)
- Internet, only for the one-time `pip install`

Milestone 1 needs no account, no API key and no payment.

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

Expected last line: **`29 passed`** (the time differs).

What the tests do and do not cover:

- Every test gets its own throw-away database in memory, so tests never touch `data\dawai.db`.
- The tests use FastAPI's `TestClient` **without** its startup step. They do **not** run the
  app's startup code (the `lifespan` in `app/main.py`, which creates the real tables).
  A green `pytest` therefore does **not** prove that the real server starts.
- That is why the manual startup check below is **mandatory**.

## Start the app

```powershell
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser (type `http://`, not `https://`).
Stop the server with **Ctrl + C**.

## Mandatory completion check for Milestone 1 (do this by hand)

Milestone 1 is finished only when **both** `pytest` passes **and** all of these are true:

1. `uvicorn app.main:app --reload` prints `Application startup complete.` and no error.
2. http://127.0.0.1:8000 shows the yellow notice, the "Server status" card and
   **"Elder profiles saved: 0"**. That number is read from the `elders` table, so seeing it
   proves the startup code created the tables.
3. http://127.0.0.1:8000/health shows `{"status":"ok","database":"ok"}`.
   (This only proves the database answers. Step 2 is the proof that the tables exist.)
4. The file `data\dawai.db` now exists (`dir data`).
5. After `git init` and `git add .`, `git status` does **not** list `.env`, `.venv` or `data/dawai.db`.

## Reset the demo database

`data\dawai.db` holds demo data only. At startup the app creates tables that are missing,
but it never changes the rules of a table that already exists. If you ran an older copy of
this project, delete the old file so the current rules (for example the corrected time rule)
are used:

```powershell
# stop the server first (Ctrl + C), then:
Remove-Item data\dawai.db
```

The next start creates a fresh one.

## What the database enforces now, and what the services must enforce later

The database is a safety net, not the whole safety system. Do **not** assume a rule is
already protected unless the first column says so.

| Rule | Enforced by the database in Milestone 1? | Who must enforce the rest |
| --- | --- | --- |
| A row cannot point to a row that does not exist (foreign keys) | **Yes** (switched on in `app/db.py` for this app's connections) | - |
| Allowed values: language, occurrence status, call channel and outcome, report type and source, notification kind, channel and delivery status | **Yes** (CHECK rules) | - |
| A schedule time is `HH:MM` from 00:00 to 23:59 | **Yes** | - |
| One occurrence per schedule item per date | **Yes** (UNIQUE) | M3 service: create it only if missing |
| One attempt number per occurrence | **Yes** (UNIQUE) | - |
| A schedule item marked "verified" has `verified_by` and `verified_at` filled in | **Yes** | M2 dashboard: require a real name, not a blank |
| Reports cannot be edited or deleted; a correction is a new row | **Yes** (two triggers; protects against mistakes in our code, not against someone editing the file with another tool) | M4: the correction feature |
| The same notification cannot be saved twice | **Yes**, if the same `dedupe_key` is used | M7: build the key the same way every time |
| Only **verified, active** schedule items create occurrences or calls | **No.** The database accepts an occurrence for an unverified item | **M3 reminder service** |
| At most two call attempts (first try plus one retry) | **No.** The database accepts attempt 3, 4, ... | **M3 reminder service** |
| A missed call never becomes a report or a "not taken" status | **No.** Nothing in the database does it automatically, but nothing forbids it either | **M3 and M4 services** |
| A report matches its occurrence and call attempt; a correction points to a report of the same occurrence; the occurrence status follows the newest report | **No.** The database accepts an inconsistent report | **M4 report service** |
| A bare "haan" is never "taken"; confusion and help are checked first; a negation beats a positive | **No.** The rule engine does not exist yet | **M4 rule engine and its safety tests** |
| The inbound history feature only reads and never writes | **No** | **M6** (read-only code, with tests) |
| A notification says "delivered" only if it was delivered | **No.** Only the three allowed values are checked | **M7 notification service** |
| Format of `repeat_days`, phone numbers and `due_time`; a non-blank `verified_by` | **No** | **M2 forms and M3 service** |

## Folders

| Folder | What lives there |
| --- | --- |
| `app/` | The application code |
| `app/routes/` | Web addresses (pages and checks). Kept short. |
| `app/services/` | The logic: reminders, rule engine, speech, alerts (added milestone by milestone) |
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
| `ModuleNotFoundError: No module named 'app'` | You are not in the project folder. `cd` into the folder that contains `pytest.ini` |
| `uvicorn` is not recognized | Activate the environment, or run `python -m uvicorn app.main:app --reload` |
| The server will not start because the address is already in use (error 10048) | Use another port: `uvicorn app.main:app --reload --port 8001` and open `http://127.0.0.1:8001` |
| The browser cannot connect | The server window was closed, or the address starts with `https`. Start `uvicorn` again and use `http://127.0.0.1:8000` |
