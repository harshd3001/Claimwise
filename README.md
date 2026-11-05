# Claimwise

Claimwise is a local employee reimbursement demo built with a React + TypeScript frontend, FastAPI backend, SQLAlchemy, and SQLite. It demonstrates the claim flow from draft through submission, approval or rejection, correction/resubmission, and payment marking.

> **Demo only:** the employee/user manager selector is a mock identity mechanism, not authentication. Do not use this app with real employee, financial, or otherwise sensitive data.

## Requirements

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+ (Node 24 is also suitable)
- npm

## Setup on Windows PowerShell

Run commands from the repository root unless noted.

### 1. Create and activate the backend virtual environment

```powershell
python --version
node --version
python -m venv .\backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python --version
```

If PowerShell prevents environment activation, either adjust the current-user execution policy according to your organization's guidance or invoke `.\backend\.venv\Scripts\python.exe` directly for backend commands.

### 2. Configure and install the backend

```powershell
if (-not (Test-Path .\backend\.env)) {
    Copy-Item .\backend\.env.example .\backend\.env
}
python -m pip install -r .\backend\requirements.txt
```

The local `.env` configures the SQLite URL and demo settings. It is intentionally ignored by Git; do not commit secrets. The local database is also ignored.
On startup, an existing local database is migrated to the User Manager role and the optional receipt-number column while preserving existing claims and history.

### 3. Start the backend

```powershell
Set-Location .\backend
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`. Leave this terminal running.

### 4. Install and start the frontend

In a second terminal, from the repository root:

```powershell
Set-Location .\frontend
npm ci
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The Vite development proxy forwards `/api` requests to the backend.

## Run tests and checks

Run the backend tests with the virtual environment activated:

```powershell
Set-Location .\backend
python -m pytest
```

Run frontend tests, type-check, and production build:

```powershell
Set-Location .\frontend
npm test
npm run typecheck
npm run build
```

For each implementation change, add or update relevant tests and run them after the change; the commands above are the wider integration checks.

## Demo workflow

The local database is preloaded with representative records in every lifecycle state: editable draft, submitted waiting for review, approved awaiting payment, rejected with reviewer feedback, partially approved and paid, and an archived draft whose audit history is retained. The demo records are seeded once by stable IDs and are not duplicated on restart. The seed can be disabled by setting `SEED_DEMO_DATA=false` in `backend\.env`.

1. Select the seeded employee identity and create a draft claim.
2. Edit the draft if needed and submit it for approval.
3. Switch to the User Manager identity and open the submitted queue.
4. Approve the claim (full or partial) or reject it, optionally adding a comment that will be saved in its history.
5. To exercise correction, switch back to the employee, reopen the rejected claim, edit it, and submit again.
6. As the User Manager, approve it and mark the approved claim paid.
7. Refresh the browser to verify that claim state and activity history persist in SQLite.

The demo employees are **Maya Employee** and **Arjun Employee**; the User Manager identity is **User Manager**. Their selector lets you inspect each role's own list and actions.

## Architecture and data model

- **React + TypeScript + Vite:** single-page UI for employees and user managers. `Design.md` defines the UI flows, styling, accessibility, and responsive behavior; read it before every frontend change.
- **FastAPI + Pydantic:** API validation, role-specific route handling, and OpenAPI documentation.
- **SQLAlchemy + SQLite:** local persistence for seeded demo users, claims, and append-only claim events.
- **Categories:** common options are seeded into the `claim_categories` table and fetched by the frontend. A custom category is saved on its claim without adding a shared category.
- **Claim amount:** stored and sent as an integer number of paise. The UI accepts rupees with at most two decimal places and formats INR for display.
- **Receipt reference:** an optional receipt/bill number is stored as text on the claim; no receipt image upload is included.
- **History:** edits record before/after details. Rejection, reopening, resubmission, approval, and payment are separate events. Draft deletion is soft deletion so its audit history remains available.
- **Concurrency:** existing-claim mutations use an ETag/`If-Match` version precondition. A stale mutation fails rather than overwriting newer work.
- **API boundary:** see [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) for routes, fields, status transitions, identity behavior, and error responses.

## Assumptions and limitations

- The demo identity selector sends a seeded user ID to the API. Anyone able to reach the local app/API can spoof it; this is not authentication or production authorization.
- SQLite is suitable for the local assignment demo, not a multi-instance production deployment.
- Marking paid records a demo status only; it does not initiate a bank transfer or integrate with a payment service.
- No receipt attachments, notifications, approval routing, or external services are included.
- Partial approval is supported only as an approval amount less than or equal to the claimed amount.

## AI-use disclosure

AI coding assistance was used to help plan and implement the application, including parallel backend/frontend workstreams. The resulting code, design, and tests should be reviewed and understood by the project owner before use or presentation.
