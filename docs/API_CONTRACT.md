# Claimwise API Contract

This contract is the shared boundary for the independently implemented FastAPI backend and React frontend. Backend OpenAPI and frontend API types must agree with it. API prefix: `/api`. JSON request/response bodies; dates are ISO `YYYY-MM-DD`; timestamps are UTC ISO-8601.

## Demo identity

- `GET /api/health` and `GET /api/users` do not require a selected identity.
- `GET /api/categories` does not require a selected identity and returns the database-backed common category names in display order.
- Every other endpoint requires `X-Demo-User-ID`.
- Stable seeded users:
  - `employee-demo` — employee, Maya Employee
  - `employee-other` — employee, Arjun Employee
  - `manager-demo` — User Manager
- Role is derived from the selected database user (`employee` or `user_manager`). The UI labels `user_manager` as “User Manager.” Never accept role from a request body. This mechanism is for local demonstration only, not authentication.
  - Local development seeds representative claims in draft, submitted, approved, rejected, paid (partial approval), and archived-draft states. This seeding is idempotent and can be disabled with `SEED_DEMO_DATA=false`.

## Domain contract

Claim statuses: `draft`, `submitted`, `approved`, `rejected`, `paid`.

The database-backed common category catalog is seeded with `Meals`, `Travel`, `Accommodation`, `Office supplies`, `Software & subscriptions`, `Communication`, `Training & education`, `Client entertainment`, and `Other`. The frontend may submit a custom category string; it is stored on that claim and does not create a shared catalog entry.

Money fields use integer paise and are limited to JavaScript's safe integer range. `amount_paise` must be positive. On approval, `approved_amount_paise` is set and must be in `[1, amount_paise]`; it defaults to the full amount. A rupee input with more than two decimal places is invalid.

Claim fields:

```text
id: string
employee_id: string
merchant: string
category: string
receipt_number: string | null
description: string
expense_date: YYYY-MM-DD
amount_paise: integer
approved_amount_paise: integer | null
status: ClaimStatus
version: positive integer
created_at: UTC datetime
updated_at: UTC datetime
deleted_at: UTC datetime | null
```

Event fields:

```text
id: string
actor_id: string
actor_name: string
action: created | updated | submitted | reopened | approved | rejected | deleted | paid
from_status: ClaimStatus | null
to_status: ClaimStatus | null
comment: string | null
details: object | null
created_at: UTC datetime
```

Events are append-only and ordered by `(created_at, id)`. Edit event `details` records changed fields' before/after values. Soft deletion records a sufficient snapshot and does not erase the claim or history.

## Endpoints

| Method and path | Behavior |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/users` | Seeded demo identities |
| `GET /api/categories` | Common claim categories from the database |
| `GET /api/me` | Current selected user |
| `GET /api/claims?status=...` | Employee's own active claims; user manager's submitted plus previously reviewed claims. Optional valid status filter. Stable newest-updated-first order. |
| `POST /api/claims` | Employee creates draft; initial version `1`, plus `created` event |
| `GET /api/claims/{id}` | Claim and ordered events; owner or user manager. Archived draft history is owner-only and read-only. Returns `ETag: "<version>"`. |
| `PATCH /api/claims/{id}` | Owner edits draft fields only |
| `DELETE /api/claims/{id}` | Owner soft-deletes draft only |
| `POST /api/claims/{id}/submit` | Owner submits a draft |
| `POST /api/claims/{id}/reopen` | Owner changes rejected claim to draft |
| `POST /api/claims/{id}/approve` | User Manager approves submitted claim |
| `POST /api/claims/{id}/reject` | User Manager rejects submitted claim |
| `POST /api/claims/{id}/mark-paid` | User Manager marks approved claim paid |

List response:

```json
{ "items": [], "total": 0 }
```

Detail response:

```json
{ "claim": {}, "events": [] }
```

Create and update request fields use the claim field names, excluding server-owned fields. Create requires the claim fields except `receipt_number`, which is optional, trimmed, and limited to 120 characters; blank values are stored as `null`. Patch accepts one or more editable fields; setting `receipt_number` to `null` clears it. Approval body:

```json
{ "approved_amount_paise": 12500, "comment": "Optional note" }
```

An omitted approval amount means full approval; the approval comment is optional and appears on the approval event in activity history. Rejecting may omit the body or provide an optional comment, which appears on the rejection event:

```json
{ "comment": "Please provide a clearer business purpose." }
```

Other action bodies are empty. Every mutation of an existing claim requires `If-Match: "<version>"`. A missing precondition returns `428`; stale version returns `412`. A successful mutation increments the version, appends exactly one event in the same transaction, returns the current claim (or detail), and includes its new ETag.

All errors use:

```json
{
  "code": "stable_machine_code",
  "message": "User-readable summary",
  "fields": {}
}
```

`fields` is optional and maps request fields to validation messages. Status codes: `401` missing/invalid identity; `403` wrong role; `404` missing or inaccessible claim; `409` invalid state transition; `412` stale `If-Match`; `422` invalid input; `428` missing required `If-Match`.

## Authorization and transitions

- Employees list/view/mutate only their own claims.
- User Managers list submitted claims and claims on which they previously acted; they can review only `submitted` and mark only `approved` as paid.
- Approval and rejection comments are optional; when supplied, they are trimmed and stored on the corresponding decision event and displayed in activity history. An omitted or blank comment is recorded as `null`.
- `draft -> submitted -> approved -> paid`
- `draft -> submitted -> rejected -> draft -> submitted` supports correction/resubmission without losing history.
- Employee edit/delete is allowed only for `draft`; deleted drafts are excluded from lists and read-only to their owner.
- Every existing-claim mutation is a conditional update on ID, expected version, status/permissions, and non-deleted state. Update and event insert are atomic. A failed precondition/transition never writes an event.
