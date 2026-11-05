<h1><img src="frontend/public/favicon.svg" alt="" width="36" height="36" /> Claimwise</h1>

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
On startup, an existing local database is migrated to the User Manager role, the optional receipt-number column, stable category IDs, and claim-to-category references. Existing claims are linked by exact catalog-name match; unmatched category names remain custom text, and every claim keeps its category-name snapshot.

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

## Architecture, data model, and design decisions

- **React + TypeScript + Vite:** single-page UI for employees and user managers. `Design.md` defines the UI flows, styling, accessibility, and responsive behavior; read it before every frontend change.
- **FastAPI + Pydantic:** API validation, role-specific route handling, and OpenAPI documentation.
- **SQLAlchemy + SQLite:** local persistence for seeded demo users, claims, and append-only claim events.
- **Users:** seeded demo identities are stored in `users`. Claims reference their employee by `employee_id`; event records reference the acting user by `actor_id` and preserve the actor name at event time.
- **Categories:** common options live in `claim_categories` with stable IDs. A claim stores both nullable `category_id` and required `category` display-name snapshot. Common choices reference the catalog; custom choices store their text with a null ID. Renaming a catalog item therefore does not rewrite existing claims.
- **Claims:** `claims` stores merchant, category snapshot/reference, optional receipt number, business description, expense date, amount, current status, version, timestamps, and soft-delete timestamp. Money is stored as integer paise; the UI accepts rupees with at most two decimal places and formats INR for display.
- **Claim events:** `claim_events` is an append-only audit trail linked to a claim and actor. Events capture actions, status transitions, optional decision comments, and edit `details` containing before/after values. Soft deletion marks a claim with `deleted_at` without removing the claim or its history.
- **Concurrency:** existing-claim mutations require an ETag/`If-Match` version precondition. A stale mutation fails rather than overwriting newer work.
- **API boundary:** see [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) for routes, fields, status transitions, identity behavior, and error responses.

The main relationships are `claims.employee_id → users.id`, optional `claims.category_id → claim_categories.id`, and `claim_events.claim_id → claims.id` plus `claim_events.actor_id → users.id`. The category name and actor name are snapshots intentionally retained alongside IDs so historical records remain understandable when catalog labels or user names change.

## Assumptions and limitations

- The demo identity selector sends a seeded user ID to the API. Anyone able to reach the local app/API can spoof it; this is not authentication or production authorization.
- SQLite is suitable for the local assignment demo, not a multi-instance production deployment.
- Marking paid records a demo status only; it does not initiate a bank transfer or integrate with a payment service.
- No receipt attachments, notifications, approval routing, or external services are included.
- Partial approval is supported only as an approval amount less than or equal to the claimed amount.

## AI-use disclosure

**Tool used:** GitHub Copilot in VS Code (AI coding assistant).

**How it was used:** to help plan the architecture, implement and refine the React/TypeScript frontend and FastAPI backend, update documentation, and create or adjust tests. The generated changes were reviewed during implementation, and the documented tests and build checks were run. The project owner should review and understand the code and design before use or presentation.
