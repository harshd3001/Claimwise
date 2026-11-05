# Claimwise — Reimbursement Management System Implementation Plan

## 1. Goal and delivery strategy

Build **Claimwise**, a working, locally runnable employee reimbursement application that demonstrates the full lifecycle:

**Create draft → submit → user manager review → approve/reject → view outcome → mark approved claim paid**

The assignment is intended for a 2–4 hour implementation. Optimize for one complete, explainable vertical slice rather than a broad but unfinished product. Keep the frontend, Python API, and SQLite persistence separate; enforce workflow rules in the backend so the UI cannot bypass them.

### Priority order

1. **P0 — Required workflow:** mocked employee/User Manager identities, draft management, submit, review, approve/reject, rejected-claim correction and resubmission, paid status, claim history.
2. **P1 — Correctness and assessment readiness:** input/state validation, ownership and role checks, duplicate/stale action handling, tests, setup documentation.
3. **P2 — Optional enhancement:** partial approval with an approved amount, without changing the lifecycle model.
4. **Defer:** real authentication, receipt uploads, notifications, payment integration, deployment, and complex approval routing.

## 2. Architecture review — issues addressed

The original plan had a sound stack and a plausible lifecycle, but it needed tighter contracts and a few audit/concurrency details before frontend and backend work could safely proceed in parallel:

- **Edit history was underspecified.** An `updated` event with no changed values would not let someone reconstruct what changed. Record before/after values for edited fields and a snapshot for soft-deleted drafts.
- **Draft deletion conflicted with durable history.** Hard-deleting a claim could cascade-delete its events. Use `deleted_at` for a soft delete, retain the deletion event, and exclude archived drafts from normal lists.
- **Parallel frontend/backend work lacked a stable boundary.** Freeze endpoint paths, schemas, identity header, status/error semantics, and version handling first. Backend OpenAPI and a frontend API adapter then provide a shared contract.
- **The mock identity mechanism is not authentication.** A caller can select/spoof a seeded identity. Treat it as a demo-only role/ownership simulation, not as a security boundary; do not put real or sensitive data in this app.
- **Concurrency language needed an implementable rule.** Use conditional updates that compare expected `version` and status, and insert the corresponding event in the same transaction. A stale/duplicate mutation must not write an event.
- **The time budget could encourage optional work before integration.** Make the required flow and integration checks a hard gate before partial approval, visual polish, or other enhancements.

The revised plan below applies these decisions and separates parallelizable work from shared-contract and integration steps.

## 3. Recommended stack and project structure

- **Backend:** Python 3, FastAPI, Pydantic, SQLAlchemy, Uvicorn.
- **Database:** SQLite, with foreign-key enforcement and a persisted local database.
- **Frontend:** React + TypeScript single-page application (SPA), built with Vite (not Next.js); use a small set of pages/components and `fetch` or one lightweight API client.
- **Backend tests:** pytest + FastAPI `TestClient`; cover domain/service rules and HTTP authorization/validation behavior.
- **Frontend tests:** Vitest + React Testing Library + `user-event`; test forms, role-specific actions, loading/error/empty states, and state updates. Use one browser-level smoke flow only if the setup remains within the time budget.
- **Configuration:** keep Python dependencies isolated in `backend/.venv`; keep local backend settings in `backend/.env`, based on a committed `backend/.env.example`. The Vite frontend uses its own non-secret config only if needed.

### Test-after-change rule

For every implementation change, add or update the closest relevant tests in the same work chunk and run them after making the change. Do not defer all test execution to final integration. Run the narrowest relevant tests first, fix failures caused by the change, then run the wider applicable suite during Chunk D. If a change has no practical automated test, document why and perform an explicit manual check. Never claim tests pass unless they were actually run.

Suggested layout:

```text
backend/
  .venv/                   # local Python environment; ignored by Git
  .env                     # local settings/secrets; ignored by Git
  .env.example             # safe documented defaults; committed
  app/
    main.py                 # app creation and router registration
    api/                    # route handlers and Pydantic request/response schemas
    models.py               # SQLAlchemy entities and constraints
    database.py             # engine, session, initialization
    services/claims.py      # lifecycle rules and transactional operations
  tests/
  requirements.txt
frontend/
  .env.example             # only if frontend config is needed; never put secrets here
  src/
    api/                    # typed API client
    components/             # status badge, form, history list
    pages/                  # employee and user manager views
    types.ts
  tests/                    # Vitest + Testing Library
  vite.config.ts            # /api proxy for local development
README.md
Design.md
plan.md
.gitignore
```

Keep route handlers thin: parse/validate requests, call the claim service, and translate known domain errors into clear HTTP responses. The service owns state transitions and writes each claim mutation and its history event in the same database transaction. Use FastAPI's generated OpenAPI schema as the source of truth for the API contract; keep frontend types aligned with it rather than independently inventing request/response shapes.

### Environment and configuration setup gate

Keep these two files distinct: `backend\.venv` is the isolated Python virtual environment (installed packages/interpreter); `backend\.env` is a local configuration file read by the backend. Create both before installing backend packages, initializing the database, or starting the API:

1. Confirm Python and Node versions; from the repository root create the virtual environment with `python -m venv .\backend\.venv`.
2. Activate it in Windows PowerShell with `.\backend\.venv\Scripts\Activate.ps1`; verify `python` and `pip` resolve inside `backend\.venv`. On macOS/Linux use `source backend/.venv/bin/activate`.
3. Copy the safe template with `Copy-Item .\backend\.env.example .\backend\.env` in PowerShell. Configure a local SQLite URL and development settings only. Do not commit `.env`, credentials, or database files; keep only non-secret examples in `.env.example`.
4. Install backend requirements using the activated environment, then initialize the local database and start FastAPI from the documented working directory.
5. Install frontend dependencies from `frontend/`; use Vite's `/api` proxy to reach FastAPI. Do not add a frontend env file unless a non-secret setting actually needs one.

Ensure `.gitignore` excludes `backend/.venv/`, all actual `.env` files (while allowing `.env.example`), local SQLite database/WAL files, Python caches, `node_modules/`, build output, and test artifacts. Provide Windows PowerShell commands in the README, with other OS instructions only if useful. Environment setup must not require committing secrets or placing backend secrets in Vite variables.

## 4. Product assumptions and workflow rules

Document these assumptions in the README and implement them consistently:

- The demo has a small seeded set of users and a mocked “log in as” selector. Send the selected seeded user ID on API requests using one documented mechanism (for example `X-Demo-User-ID`). This is a development convenience, **not authentication**: a caller can spoof the header, so this is not a security boundary and must not be used with sensitive data.
- Seed stable, idempotent demo claims for every status plus a partially approved paid claim and a soft-deleted draft with retained history. Gate sample-claim seeding with `SEED_DEMO_DATA` so test databases can stay clean; seed at app startup for local demo use and never duplicate records on restart.
- Every claim belongs to exactly one employee. Employees may only view or change their own claims; user managers may review submitted claims.
- A draft requires a merchant, category, expense date, description, and positive amount. Trim required text; use documented limits such as merchant ≤120 characters, category ≤60, and description ≤1,000. Parse the expense date as an ISO date. Do not invent extra expense-date rules beyond valid date input. Use integer **paise** in storage to avoid floating-point currency errors; display INR/rupees in the UI. Keep API amounts within JavaScript's safe-integer range so JSON clients do not silently round them.
- Seed common categories in a database table and expose them through a public read endpoint. The form offers these choices plus a custom-entry option; custom values are saved on an individual claim and do not mutate the shared catalog.
- Employee changes are allowed only while a claim is a draft. Deletion is allowed only for a draft.
- Submission is allowed only from `draft`. User Managers act only on `submitted` claims.
- Rejection comments are optional; when supplied, save them on the rejection event. A rejected claim may be returned to `draft` by its employee for correction, then submitted again. This preserves a simple lifecycle while the event log retains every prior submission and decision.
- Approval may be full or partial. For partial approval, `0 < approved_amount <= claimed_amount`; use the claimed amount when the user manager selects full approval.
- Only approved claims may be marked `paid`. Payment is a demo status change, with no external payment operation.
- Every create, edit, submit, reopen, review decision, soft-delete, and paid action records an event with actor and timestamp. For edits, record changed fields and their before/after values; for deletion, retain a snapshot sufficient to understand the deleted draft. Store comments on the relevant review event; do not overwrite prior decisions.
- Repeating an action after the claim has changed state, or acting on a stale version, returns a clear conflict instead of applying another transition or duplicating history.
- Every successful mutation of an existing claim, including draft edits and soft deletion, increments `version`; creation initializes it to `1`. The frontend sends the version it last read with each existing-claim mutation; a mismatch requires reloading the claim.
- Keep actions explicit: rejection returns a claim to `rejected`; the employee separately reopens it to `draft`, edits it, and submits it again. A new review is a new event in the same claim history.

## 5. Data model

### `users`

| Field | Purpose |
|---|---|
| `id` | Primary key |
| `name` | Display name |
| `email` | Stable demo identity |
| `role` | `employee` or `user_manager` (displayed as “User Manager”) |

Seed at least one employee and one user manager. Keep role values constrained to the supported set.

### `claims`

| Field | Purpose |
|---|---|
| `id` | Primary key (UUID or integer, consistently used by API and UI) |
| `employee_id` | Owner; foreign key to `users` |
| `merchant`, `category`, `description` | Claim details |
| `receipt_number` | Optional receipt/bill reference, stored as text to preserve letters and leading zeros |
| `expense_date` | Date the expense occurred |
| `amount_paise` | Positive claimed amount in integer paise |
| `approved_amount_paise` | Null before approval; set to the authorized amount on approval |
| `status` | `draft`, `submitted`, `approved`, `rejected`, or `paid` |
| `version` | Incremented on each mutation; used to detect stale concurrent actions |
| `created_at`, `updated_at` | UTC timestamps |
| `deleted_at` | Nullable UTC timestamp; set only when a draft is deleted, so history remains available |

### `claim_categories`

Seed common category names in display order and return them from `GET /api/categories`. A custom category is accepted on a claim but does not mutate this shared list.

Use database constraints where practical (positive safe-range amount, valid status, valid foreign keys, and `approved_amount_paise <= amount_paise` when non-null); repeat essential checks in the service layer to return helpful validation errors. The API accepts integer paise for monetary fields; the UI parses the rupee input as a decimal string with at most two decimal places and converts it to paise without floating-point rounding.

### `claim_events`

| Field | Purpose |
|---|---|
| `id` | Primary key |
| `claim_id` | Foreign key to `claims` |
| `actor_id` | User who performed the action |
| `action` | Such as `created`, `updated`, `submitted`, `reopened`, `approved`, `rejected`, or `paid` |
| `from_status`, `to_status` | State transition audit |
| `comment` | Optional note for approval or rejection |
| `details_json` | Optional structured before/after values for edits and a deletion snapshot |
| `created_at` | UTC event time |

Index `claims(employee_id, status)` and `claim_events(claim_id, created_at, id)` for the principal list/history queries. Return events ordered by `created_at, id` for deterministic ordering. Keep history append-only through the application; do not implement event edits or deletes. Normal claim lists exclude rows with `deleted_at` set.

## 6. API and authorization outline

Use the documented demo-user header consistently on `/api/me` and every claim endpoint. The demo-only `GET /api/users` may be called before identity selection and returns only the seeded demo identities. Validate the selected ID belongs to a seeded user; derive role from that user record and never accept role from a request body. Clearly label this limitation in the UI and README. Use the Vite development proxy for `/api` to avoid unnecessary local CORS configuration.

Suggested endpoints:

| Endpoint | Access | Behavior |
|---|---|---|
| `GET /api/users` | Demo | Return selectable seeded users |
| `GET /api/me` | Demo | Return the selected identity and role |
| `GET /api/claims` | Employee / user manager | Employee sees own non-deleted claims; user manager sees submitted and previously reviewed claims |
| `POST /api/claims` | Employee | Create a draft and its initial history event |
| `GET /api/claims/{id}` | Owner / user manager | Return claim details and ordered event history; archived drafts are read-only and owner-only |
| `PATCH /api/claims/{id}` | Owner | Edit a draft only |
| `DELETE /api/claims/{id}` | Owner | Soft-delete a draft only; retain its event history |
| `POST /api/claims/{id}/submit` | Owner | Submit a draft or corrected draft |
| `POST /api/claims/{id}/reopen` | Owner | Move rejected claim to draft for correction |
| `POST /api/claims/{id}/approve` | User Manager | Approve fully or partially, with optional comment |
| `POST /api/claims/{id}/reject` | User Manager | Reject with optional comment |
| `POST /api/claims/{id}/mark-paid` | User Manager | Mark an approved claim paid |

Use consistent response schemas, ISO-formatted dates/timestamps, and explicit error responses. For list behavior, define an optional status filter and stable ordering; return an `items` array with only fields needed by list views. Each list item includes `version`; claim detail returns the full claim and ordered history. The claim response includes `id`, `employee_id`, `merchant`, `category`, `description`, `expense_date`, `amount_paise`, nullable `approved_amount_paise`, `status`, `version`, `created_at`, `updated_at`, and nullable `deleted_at`; detail adds ordered `events`. Every mutation of an existing claim carries `If-Match: "<version>"`; detail and create/mutation responses expose an ETag for the current version. Claim creation initializes version `1` and needs no precondition. Approval and rejection may carry an optional `comment`; other actions need no extra fields. Normalize domain and Pydantic validation errors to one documented shape, for example `{ "code": "...", "message": "...", "fields": {} }`, with `fields` optional. User Managers' list includes the submitted queue and claims with a prior review decision; employees' list contains their own non-deleted claims. Archived drafts remain retrievable by their owner for read-only history, but are not listed by default. Keep IDs, field names, nullable values, and amount units identical across OpenAPI and frontend types.

- `401` for missing/invalid demo identity (if represented as authentication).
- `403` for a valid identity without permission.
- `404` for a missing claim (and optionally inaccessible records if avoiding ownership disclosure).
- `409` for invalid lifecycle transitions.
- `412` for a stale `If-Match` version.
- `422` for malformed or out-of-range data.

Require `If-Match` on every mutation of an existing claim. Perform a conditional update comparing claim ID, version, expected status, and `deleted_at IS NULL`; append the event in the same transaction only if exactly one row was updated. If no row matches, do not append an event and return `412` for a stale version or `404` for a missing/inaccessible claim. Configure a modest SQLite busy timeout (for example, 5 seconds). This guards against accidental double-clicks and stale concurrent actions without adding a queue/locking subsystem.

## 7. Frontend experience

Keep the UI intentionally small and focused on completing the workflow:

1. **Demo identity selector:** switch between seeded employee and user manager; show the current role and a clear demo-only notice.
2. **Employee claims view:** status-filtered list, create/edit draft form, draft deletion confirmation, claim detail/history, submit action, and a clear rejected-claim correction/resubmit path.
3. **User Manager view:** submitted-claims queue, claim details and event history, approve (full by default; optional approved-amount input), reject with optional comment, and a previously reviewed list.
4. **Outcome and payment:** show claimed and approved amounts, reviewer comments, status, and a mark-paid action only for approved claims.

UI behavior:

- Render loading, empty, success, and error states; do not silently treat failed requests as success.
- Disable actions while a request is pending and refresh the claim/list after a successful mutation.
- Display validation near form fields and server-side conflict messages in an actionable way.
- Format money using INR formatting while converting to/from integer paise at the API boundary.
- Use semantic labels/buttons and basic keyboard accessibility.
- Follow [Design.md](Design.md) as the required source of truth before every frontend UI, interaction, or styling change. If a product requirement conflicts with it, update and reconcile the design document first; do not silently diverge.
- Keep user-facing copy plain, reassuring, and specific: explain what happened, what is needed next, and how to recover from an error. Ask for confirmation before destructive actions and show a success confirmation after important actions.

## 8. Parallel execution plan and dependencies

Parallel work is safe only after agreeing on the API contract and shared domain terms. Keep the frontend and backend in separate directories and assign file ownership to avoid conflicting edits. If working solo, execute the same chunks in dependency order; parallelism is an option, not a reason to skip integration.

### Chunk 0 — Shared decisions and contract (sequential gate; 10–15 min)

Agree on product name (Claimwise), statuses, field names, `amount_paise` units, demo-user header exception for demo-user discovery, endpoint paths, request/response examples, error format, and `If-Match`/ETag rules. Review [Design.md](Design.md) before assigning frontend work and align its flows with the contract. Add a small contract table and Pydantic schemas before splitting work; FastAPI's generated OpenAPI is then the implemented contract to compare against the table. Decide that deleting a draft means soft deletion.

Before any backend package installation or server startup, create and activate `backend/.venv`, create `backend/.env` from `.env.example`, verify the active interpreter, and establish `.gitignore` rules. Do not copy real credentials into source control. No frontend/backend parallel implementation starts until the API contract, design guide, environment setup, and file ownership are clear.

**Output:** stable API contract, design guide, isolated Python environment/configuration, project skeleton, and per-directory ownership.

### Chunk A — Backend and persistence (parallel after Chunk 0; 60–90 min)

Own `backend/app/`. Implement SQLite setup/foreign keys, idempotent demo-user seeding, SQLAlchemy entities, claim service, and API routes. Implement role/owner checks, event details for edits, soft deletion, conditional versioned updates, and transaction boundaries. Do not edit `backend/tests/` or `README.md`; those belong to Chunk C.

**Depends on:** Chunk 0.  
**Can run alongside:** Chunks B and C.  
**Done when:** API routes and OpenAPI match Chunk 0; backend tests are added/updated and run after implementation, and Chunk C's API tests pass for the required lifecycle.

### Chunk B — Frontend shell and screens (parallel after Chunk 0; 50–75 min)

Own `frontend/`. Read and follow [Design.md](Design.md) before changing any frontend files. Build React + TypeScript + Vite identity selector, employee list/form/detail/history, user manager queue/detail/decision controls, and loading/error/empty states. Use a typed API adapter matching Chunk 0; while the API is unavailable, use a small local mock implementation behind that adapter rather than embedding mock data in components. Configure the Vite `/api` proxy. Add frontend tests with Vitest and React Testing Library for the primary user interactions and critical UI states.

**Depends on:** Chunk 0.  
**Can run alongside:** Chunks A and C.  
**Done when:** screens and interactions work against the mock adapter and can be switched to the real API without changing components; relevant frontend tests are added/updated and run after each implementation change.

### Chunk C — Contract-based test matrix and handoff docs (parallel after Chunk 0; 25–40 min)

Own `backend/tests/` for agreed acceptance cases and `README.md` for setup, demo identities, assumptions, limitations, data model, and AI-use disclosure. Coordinate test expectations with the backend owner; do not edit `backend/app/` or frontend files. Tests may be authored against Chunk 0's contract and run once the relevant backend endpoints are ready. Document virtual-environment creation/activation, `.env` setup, and run/test commands from the actual scaffold rather than guessing them.

**Depends on:** Chunk 0.  
**Can run alongside:** Chunks A and B.  
**Done when:** backend and frontend tests cover the agreed acceptance matrix; tests are run after related changes and README commands are verified during integration.

### Chunk D — Integration and required-flow verification (sequential; 25–40 min)

Wire the frontend adapter to the real API; compare actual OpenAPI schemas with frontend types; verify the Vite proxy, identity-header, amount-unit, status-code, and stale-version behavior. Run the full backend test suite, frontend unit/component tests, and frontend type-check/build after integration. Complete a browser/manual flow through draft → submit → reject → reopen/edit/resubmit → approve → paid, then reload to verify SQLite persistence and event history. Check all screens against [Design.md](Design.md), including keyboard operation, narrow viewport, and visible success/error feedback.

**Depends on:** A, B, and C complete.  
**Done when:** the browser can perform the required flow, the data persists, and automated checks pass.

### Chunk E — Optional partial approval and polish (only after D passes; 15–30 min)

Add/use `approved_amount_paise`, enforce the inclusive range `1..amount_paise`, display claimed and approved amounts distinctly, and add focused tests. Spend remaining time on usability, not new infrastructure.

**Depends on:** D.  
**Done when:** optional behavior works without regressing the required flow. Skip this chunk if time is short.

### Suggested elapsed time

With separate contributors, A, B, and C run concurrently: the expected critical path is about 95–145 minutes including the contract gate and integration, plus 15–30 minutes if Chunk E is attempted. These estimates assume parallel contributors and are approximate. A solo developer should budget for the workstreams cumulatively, skip Chunk E, and trim visual polish; never skip Chunk D or the mandatory lifecycle checks.

## 9. Test plan and acceptance criteria

### Backend tests

- Valid draft creation; required fields; amount must be a positive integer number of paise. UI rejects rupee values with more than two decimal places.
- API validation errors have the documented response shape; malformed/missing demo identity and invalid role/ownership are handled consistently.
- Employee cannot view or mutate another employee’s claim; employee cannot review or mark paid.
- User Manager cannot edit/delete employee drafts; employee cannot approve/reject or mark paid.
- Only valid state transitions succeed; invalid transitions return conflict and do not append events.
- Rejection without a comment fails; valid rejection records actor, comment, and transition.
- Rejected claim can be reopened, edited, and resubmitted; previous decisions remain in history.
- Full and partial approvals; reject zero, negative, or greater-than-claimed approved amounts.
- Only approved claims can be marked paid; repeated mark-paid/review requests do not create duplicate events.
- Stale-version mutation is rejected without a partial claim update or orphan event; two mutations using the same version result in at most one success.
- Draft soft deletion hides it from ordinary lists but retains a deletion event and readable audit snapshot.
- Edit history records before/after values; list results are role-scoped and history is deterministically ordered with each actor/action/comment.

### Frontend tests

- Employee can create a valid draft, sees field-level validation for invalid/incomplete data, and can edit/submit only when allowed.
- Rejected claim shows the reviewer comment and the correction/reopen/resubmit path; prior events remain visible.
- User Manager can review a submitted claim, can reject with or without a comment, sees a clear approval outcome, and can mark only approved claims paid.
- Role switching changes available actions and refreshes role-scoped data; a stale mutation shows a recoverable conflict and reload option.
- Loading, empty, network/API error, and success states render clearly; controls prevent duplicate submissions while a request is pending.
- Money parsing/formatting covers whole rupees, paise, invalid precision, and safe integer boundaries.
- Key flows are keyboard accessible and remain usable at mobile widths; status remains understandable without color alone.

Use API-client mocks (or MSW if already installed) for isolated component tests. Keep a small number of high-value tests per journey rather than snapshot-testing implementation details. Backend tests should use a temporary isolated SQLite database and deterministic seeded users; do not depend on the developer's local database. Run the tests after each related change and the complete frontend/backend suites after integration.

### End-to-end acceptance

- Employee creates a draft, edits it, and submits it.
- User Manager sees the submitted claim, reviews it, and approves or rejects it, optionally adding a comment.
- Employee can inspect the outcome and history; after rejection, they can correct and resubmit.
- User Manager can mark an approved claim paid.
- Optional: user manager can approve less than the claimed amount, and both amounts are displayed distinctly.
- Data remains after frontend refresh/backend restart; setup instructions are sufficient for a fresh local run.

## 10. Risks, trade-offs, and mitigations

| Risk | Mitigation |
|---|---|
| Time budget encourages implementing UI before workflow rules | Complete and test the backend lifecycle first, then build only the screens needed to exercise it. |
| Mock login could be mistaken for real access control | Keep it visibly demo-only, derive role from the selected seeded user, and enforce role/ownership in every route. |
| Floating-point money calculations | Persist integer paise; validate and format at request/UI boundaries. |
| Duplicate or concurrent reviewer actions | Require the current claim version and expected state; update and append history atomically. |
| Resubmission or edits lose audit detail | Keep one claim record but append events with before/after edit values for every correction, submission, and decision. |
| Hard deletion removes the audit trail | Soft-delete drafts and retain an event snapshot; exclude deleted drafts from ordinary lists. |
| Frontend and backend drift while parallelized | Freeze the OpenAPI contract first; compare it during integration and keep a single source of truth for units and field names. |
| SQLite schema changes during rapid iteration | Keep the schema small and document that local database reset is acceptable during development; use migrations only if time/setup already supports them. |
| Optional features crowd out required flow | Treat partial approval as P2; do not start it until all mandatory acceptance checks pass. |

## 11. Definition of done

- The required lifecycle works end-to-end through the UI and persists in SQLite.
- Employee/user manager capabilities and ownership rules are enforced server-side.
- Claim history records actors, actions, transitions, timestamps, and review comments.
- Edits and draft deletion retain enough audit detail; normal lists do not show soft-deleted drafts.
- Invalid amounts, invalid transitions, duplicate/stale actions, and rejected-claim resubmission are handled deliberately.
- Relevant tests were added/updated and run after changes; the full applicable test suites pass, frontend types match the API, and the frontend builds.
- Frontend and backend test suites pass; tests are repeatable without production/local data.
- README documents the Claimwise name, setup (including `backend/.venv` and `backend/.env`), demo usage, assumptions, data model/design decisions, known limitations, and AI usage.
- All frontend work follows [Design.md](Design.md); the design is usable with keyboard, screen-reader semantics, and narrow viewports.
