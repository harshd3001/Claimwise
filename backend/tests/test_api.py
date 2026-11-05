from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import identity, sample_claim
from app.database import (
    DEFAULT_CATEGORIES,
    DEMO_CLAIMS,
    _migrate_claim_receipt_number,
    _migrate_legacy_user_manager_role,
    create_database,
    initialize_database,
)
from app.main import create_app
from app.models import Claim, ClaimCategory, User


def create_claim(
    client: TestClient,
    *,
    user_id: str = "employee-demo",
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/claims",
        headers=identity(user_id),
        json=values or sample_claim(),
    )
    assert response.status_code == 201, response.text
    assert response.headers["etag"] == '"1"'
    return response.json()


def mutate(
    client: TestClient,
    claim_id: str,
    action: str,
    version: int,
    *,
    user_id: str = "employee-demo",
    body: dict[str, Any] | None = None,
) -> Any:
    headers = {**identity(user_id), "If-Match": f'"{version}"'}
    if body is None:
        return client.post(f"/api/claims/{claim_id}/{action}", headers=headers)
    return client.post(f"/api/claims/{claim_id}/{action}", headers=headers, json=body)


def detail(client: TestClient, claim_id: str, user_id: str = "employee-demo") -> dict[str, Any]:
    response = client.get(f"/api/claims/{claim_id}", headers=identity(user_id))
    assert response.status_code == 200, response.text
    return response.json()


def assert_error(response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    data = response.json()
    assert data["code"] == code
    assert isinstance(data["message"], str)
    assert isinstance(data["fields"], dict)
    return data


def test_health_users_identity_and_stable_seed(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}
    initialize_database(client.app.state.engine, client.app.state.sessions)
    with client.app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
    users = client.get("/api/users")
    assert users.status_code == 200
    assert [(user["id"], user["role"]) for user in users.json()] == [
        ("employee-demo", "employee"),
        ("employee-other", "employee"),
        ("manager-demo", "user_manager"),
    ]
    assert_error(client.get("/api/me"), 401, "identity_required")
    assert_error(client.get("/api/me", headers=identity("missing")), 401, "invalid_identity")
    assert client.get("/api/me", headers=identity("manager-demo")).json()["role"] == "user_manager"
    categories = client.get("/api/categories")
    assert categories.status_code == 200
    assert [category["name"] for category in categories.json()] == list(DEFAULT_CATEGORIES)
    assert all(category["id"] for category in categories.json())
    assert len({category["id"] for category in categories.json()}) == len(DEFAULT_CATEGORIES)
    openapi = client.get("/openapi.json").json()
    assert openapi["paths"]["/api/claims"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]["$ref"] == "#/components/schemas/ErrorOut"
    assert openapi["paths"]["/api/claims/{claim_id}/submit"]["post"]["responses"]["428"][
        "content"
    ]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorOut"
    assert "401" not in openapi["paths"]["/api/categories"]["get"]["responses"]


def test_custom_claim_category_does_not_change_category_catalog(client: TestClient):
    categories_before = client.get("/api/categories").json()
    claim = create_claim(client, values=sample_claim(category="Volunteer support"))

    assert claim["category"] == "Volunteer support"
    assert claim["category_id"] is None
    assert client.get("/api/categories").json() == categories_before


def test_catalog_category_id_is_stored_and_validated(client: TestClient):
    category = next(
        option for option in client.get("/api/categories").json()
        if option["name"] == "Meals"
    )
    claim = create_claim(
        client,
        values=sample_claim(category="Meals", category_id=category["id"]),
    )

    assert claim["category"] == "Meals"
    assert claim["category_id"] == category["id"]

    mismatch = client.post(
        "/api/claims",
        headers=identity(),
        json=sample_claim(category="Travel", category_id=category["id"]),
    )
    assert_error(mismatch, 422, "validation_error")


def test_category_migration_preserves_existing_names_and_claim_snapshots():
    engine, sessions = create_database("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE claim_categories (name VARCHAR(60) PRIMARY KEY, sort_order INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO claim_categories (name, sort_order) VALUES ('Meals', 0), ('Local travel', 1)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE claims (id TEXT PRIMARY KEY, category TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO claims (id, category) VALUES "
            "('existing-claim', 'Meals'), ('custom-claim', 'Volunteer support')"
        )

    initialize_database(engine, sessions)
    with engine.connect() as connection:
        migrated_categories = connection.exec_driver_sql(
            "SELECT id, name, sort_order FROM claim_categories ORDER BY sort_order"
        ).all()
        claim_category = connection.exec_driver_sql(
            "SELECT category, category_id FROM claims WHERE id='existing-claim'"
        ).one()
        custom_category_id = connection.exec_driver_sql(
            "SELECT category_id FROM claims WHERE id='custom-claim'"
        ).scalar_one()

    assert migrated_categories[0].name == "Meals"
    assert migrated_categories[0].sort_order == 0
    assert "Local travel" in {row.name for row in migrated_categories}
    assert set(DEFAULT_CATEGORIES).issubset({row.name for row in migrated_categories})
    assert all(row.id for row in migrated_categories)
    assert claim_category.category == "Meals"
    assert claim_category.category_id == migrated_categories[0].id
    assert custom_category_id is None

    initialize_database(engine, sessions)
    with engine.connect() as connection:
        categories_after_restart = connection.exec_driver_sql(
            "SELECT id, name FROM claim_categories ORDER BY sort_order"
        ).all()
        claim_after_restart = connection.exec_driver_sql(
            "SELECT category, category_id FROM claims WHERE id='existing-claim'"
        ).one()
    assert [(row.id, row.name) for row in categories_after_restart] == [
        (row.id, row.name) for row in migrated_categories
    ]
    assert claim_after_restart.category == "Meals"
    assert claim_after_restart.category_id == migrated_categories[0].id
    engine.dispose()


def test_renaming_catalog_category_does_not_change_existing_claim_category(client: TestClient):
    claim = create_claim(client, values=sample_claim(category="Meals"))
    with client.app.state.sessions.begin() as session:
        category = session.query(ClaimCategory).filter_by(name="Meals").one()
        category.name = "Food & meals"
        category_id = category.id

    initialize_database(client.app.state.engine, client.app.state.sessions)
    category_response = client.get("/api/categories")
    assert {"id": category_id, "name": "Food & meals"} in category_response.json()
    claim_after_rename = client.get(
        f"/api/claims/{claim['id']}", headers=identity()
    ).json()["claim"]
    assert claim_after_rename["category"] == "Meals"
    assert claim_after_rename["category_id"] == category_id


def test_category_id_patch_updates_reference_and_custom_name_snapshot(client: TestClient):
    claim = create_claim(client, values=sample_claim(category="Meals"))
    categories = {
        category["name"]: category["id"]
        for category in client.get("/api/categories").json()
    }

    updated = client.patch(
        f"/api/claims/{claim['id']}",
        headers={**identity(), "If-Match": '"1"'},
        json={"category": "Travel", "category_id": categories["Travel"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["category"] == "Travel"
    assert updated.json()["category_id"] == categories["Travel"]

    custom = client.patch(
        f"/api/claims/{claim['id']}",
        headers={**identity(), "If-Match": '"2"'},
        json={"category": "Team event", "category_id": None},
    )
    assert custom.status_code == 200, custom.text
    assert custom.json()["category"] == "Team event"
    assert custom.json()["category_id"] is None


def test_saving_other_fields_after_catalog_rename_preserves_category_snapshot(client: TestClient):
    claim = create_claim(client, values=sample_claim(category="Meals"))
    with client.app.state.sessions.begin() as session:
        category = session.query(ClaimCategory).filter_by(name="Meals").one()
        category.name = "Food & meals"

    updated = client.patch(
        f"/api/claims/{claim['id']}",
        headers={**identity(), "If-Match": '"1"'},
        json={"description": "Updated purpose", "category": "Meals", "category_id": claim["category_id"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["category"] == "Meals"
    assert updated.json()["category_id"] == claim["category_id"]


def test_optional_receipt_number_is_trimmed_and_can_be_updated(client: TestClient):
    claim = create_claim(
        client,
        values=sample_claim(receipt_number="  INV-007-A  "),
    )
    assert claim["receipt_number"] == "INV-007-A"

    response = client.patch(
        f"/api/claims/{claim['id']}",
        headers={**identity(), "If-Match": '"1"'},
        json={"receipt_number": " BILL-0002 "},
    )

    assert response.status_code == 200
    assert response.json()["receipt_number"] == "BILL-0002"

    cleared = client.patch(
        f"/api/claims/{claim['id']}",
        headers={**identity(), "If-Match": '"2"'},
        json={"receipt_number": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["receipt_number"] is None


def test_receipt_number_is_optional_and_blank_values_become_null(client: TestClient):
    without_receipt = create_claim(client)
    blank_receipt = create_claim(client, values=sample_claim(receipt_number="   "))

    assert without_receipt["receipt_number"] is None
    assert blank_receipt["receipt_number"] is None


def test_migrate_existing_claims_adds_nullable_receipt_number():
    engine, _ = create_database("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE claims (id TEXT PRIMARY KEY, merchant TEXT)")
        connection.exec_driver_sql("INSERT INTO claims (id, merchant) VALUES ('claim-existing', 'Cafe')")

    _migrate_claim_receipt_number(engine)

    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT id, merchant, receipt_number FROM claims WHERE id='claim-existing'"
        ).one()
        assert row == ("claim-existing", "Cafe", None)
    engine.dispose()


def test_optional_sample_claims_cover_lifecycle_and_seed_idempotently(client: TestClient):
    engine = client.app.state.engine
    sessions = client.app.state.sessions
    initialize_database(engine, sessions, seed_sample_data=True)
    initialize_database(engine, sessions, seed_sample_data=True)

    employee_claims = client.get("/api/claims", headers=identity()).json()["items"]
    assert {claim["status"] for claim in employee_claims} == {
        "draft",
        "submitted",
        "rejected",
    }
    assert all(claim["employee_id"] == "employee-demo" for claim in employee_claims)

    other_employee_claims = client.get(
        "/api/claims",
        headers=identity("employee-other"),
    ).json()["items"]
    assert {claim["status"] for claim in other_employee_claims} == {"approved", "paid"}
    assert all(claim["employee_id"] == "employee-other" for claim in other_employee_claims)

    manager_claims = client.get(
        "/api/claims",
        headers=identity("manager-demo"),
    ).json()["items"]
    assert {claim["status"] for claim in manager_claims} == {
        "submitted",
        "approved",
        "rejected",
        "paid",
    }
    assert "draft" not in {claim["status"] for claim in manager_claims}
    assert client.get("/api/claims", headers=identity()).json()["total"] == 3

    with sessions() as session:
        for sample in DEMO_CLAIMS:
            claim = session.get(Claim, sample["id"])
            assert claim is not None
            assert claim.version == len(sample["events"])
            assert len(claim.events) == len(sample["events"])
            for event in claim.events:
                assert event.actor_name in {"Maya Employee", "Arjun Employee", "User Manager"}

    archived = client.get(
        "/api/claims/demo-claim-archived",
        headers=identity(),
    ).json()
    assert archived["claim"]["deleted_at"] is not None
    assert archived["events"][-1]["action"] == "deleted"
    assert archived["events"][-1]["details"] is None
    assert archived["claim"]["merchant"] == "Sample Store"


def test_create_edit_list_and_edit_audit(client: TestClient):
    claim = create_claim(client)
    assert claim["merchant"] == "Metro Cafe"
    assert claim["status"] == "draft"
    assert claim["version"] == 1
    assert claim["expense_date"] == "2026-10-28"
    assert claim["approved_amount_paise"] is None

    response = client.patch(
        f"/api/claims/{claim['id']}",
        headers={**identity(), "If-Match": '"1"'},
        json={"merchant": " Station Cafe ", "amount_paise": 13000},
    )
    assert response.status_code == 200, response.text
    assert response.headers["etag"] == '"2"'
    assert response.json()["version"] == 2
    assert response.json()["merchant"] == "Station Cafe"

    data = detail(client, claim["id"])
    assert [event["action"] for event in data["events"]] == ["created", "updated"]
    assert data["events"][1]["details"] == {
        "changes": {
            "merchant": {"before": "Metro Cafe", "after": "Station Cafe"},
            "amount_paise": {"before": 12500, "after": 13000},
        }
    }
    listing = client.get("/api/claims", headers=identity()).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == claim["id"]
    assert listing["items"][0]["version"] == 2
    assert client.get("/api/claims?status=paid", headers=identity()).json() == {
        "items": [],
        "total": 0,
    }


def test_role_and_owner_guards(client: TestClient):
    claim = create_claim(client)
    assert_error(client.get(f"/api/claims/{claim['id']}", headers=identity("employee-other")), 404, "not_found")
    assert_error(
        client.patch(
            f"/api/claims/{claim['id']}",
            headers={**identity("employee-other"), "If-Match": '"1"'},
            json={"merchant": "Other"},
        ),
        404,
        "not_found",
    )
    assert_error(
        client.post(
            "/api/claims",
            headers=identity("manager-demo"),
            json=sample_claim(),
        ),
        403,
        "forbidden",
    )
    assert_error(
        client.post(
            f"/api/claims/{claim['id']}/submit",
            headers={**identity("manager-demo"), "If-Match": '"1"'},
        ),
        403,
        "forbidden",
    )
    assert_error(
        client.post(
            f"/api/claims/{claim['id']}/approve",
            headers={**identity(), "If-Match": '"1"'},
            json={},
        ),
        403,
        "forbidden",
    )
    assert_error(
        client.post(
            f"/api/claims/{claim['id']}/mark-paid",
            headers={**identity(), "If-Match": '"1"'},
        ),
        403,
        "forbidden",
    )
    assert_error(
        client.patch(
            f"/api/claims/{claim['id']}",
            headers={**identity("manager-demo"), "If-Match": '"1"'},
            json={"merchant": "Should not edit"},
        ),
        403,
        "forbidden",
    )
    assert_error(
        client.delete(
            f"/api/claims/{claim['id']}",
            headers={**identity("manager-demo"), "If-Match": '"1"'},
        ),
        403,
        "forbidden",
    )
    assert len(detail(client, claim["id"])["events"]) == 1


def test_validation_errors_use_contract_shape_and_enforce_paise(client: TestClient):
    missing = client.post("/api/claims", headers=identity(), json={"merchant": "Shop"})
    error = assert_error(missing, 422, "validation_error")
    assert "amount_paise" in error["fields"]

    for bad_amount in (0, -1, 1.25, True, 9_007_199_254_740_992):
        response = client.post(
            "/api/claims",
            headers=identity(),
            json=sample_claim(amount_paise=bad_amount),
        )
        assert_error(response, 422, "validation_error")

    invalid_date = client.post(
        "/api/claims",
        headers=identity(),
        json=sample_claim(expense_date="2026-02-30"),
    )
    assert "expense_date" in assert_error(invalid_date, 422, "validation_error")["fields"]

    blank = client.post("/api/claims", headers=identity(), json=sample_claim(description="  "))
    assert "description" in assert_error(blank, 422, "validation_error")["fields"]
    extra_role = client.post(
        "/api/claims",
        headers=identity(),
        json=sample_claim(role="user_manager"),
    )
    assert "role" in assert_error(extra_role, 422, "validation_error")["fields"]


def test_invalid_transitions_and_failures_never_append_events(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    assert_error(mutate(client, claim_id, "approve", 1, user_id="manager-demo", body={}), 409, "invalid_transition")
    assert_error(mutate(client, claim_id, "mark-paid", 1, user_id="manager-demo"), 409, "invalid_transition")
    assert_error(mutate(client, claim_id, "reopen", 1), 409, "invalid_transition")
    assert_error(mutate(client, claim_id, "submit", 1, user_id="employee-other"), 404, "not_found")
    assert_error(
        client.patch(
            f"/api/claims/{claim_id}",
            headers={**identity(), "If-Match": '"1"'},
            json={},
        ),
        422,
        "validation_error",
    )
    assert len(detail(client, claim_id)["events"]) == 1
    assert detail(client, claim_id)["claim"]["version"] == 1


def test_reject_reopen_edit_resubmit_preserves_ordered_history(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    assert mutate(client, claim_id, "submit", 1).status_code == 200
    rejected = mutate(
        client,
        claim_id,
        "reject",
        2,
        user_id="manager-demo",
        body={"comment": "Please clarify the business purpose."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["version"] == 3
    assert mutate(client, claim_id, "reopen", 3).json()["status"] == "draft"
    updated = client.patch(
        f"/api/claims/{claim_id}",
        headers={**identity(), "If-Match": '"4"'},
        json={"description": "Clarified client meeting lunch"},
    )
    assert updated.status_code == 200
    assert mutate(client, claim_id, "submit", 5).json()["status"] == "submitted"

    events = detail(client, claim_id)["events"]
    assert [event["action"] for event in events] == [
        "created",
        "submitted",
        "rejected",
        "reopened",
        "updated",
        "submitted",
    ]
    event_order = [(event["created_at"], event["id"]) for event in events]
    assert event_order == sorted(event_order)
    assert events[2]["comment"] == "Please clarify the business purpose."
    assert events[4]["details"]["changes"]["description"] == {
        "before": "Client meeting lunch",
        "after": "Clarified client meeting lunch",
    }
    assert [event["actor_id"] for event in events] == [
        "employee-demo",
        "employee-demo",
        "manager-demo",
        "employee-demo",
        "employee-demo",
        "employee-demo",
    ]


def test_rejection_without_comment_is_allowed_and_records_null_comment(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    assert mutate(client, claim_id, "submit", 1).status_code == 200

    rejected = mutate(client, claim_id, "reject", 2, user_id="manager-demo")

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    events = detail(client, claim_id)["events"]
    assert events[-1]["action"] == "rejected"
    assert events[-1]["comment"] is None


def test_blank_rejection_comment_is_recorded_as_null(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    assert mutate(client, claim_id, "submit", 1).status_code == 200

    rejected = mutate(
        client,
        claim_id,
        "reject",
        2,
        user_id="manager-demo",
        body={"comment": "   "},
    )

    assert rejected.status_code == 200
    assert detail(client, claim_id)["events"][-1]["comment"] is None


def test_legacy_reviewer_role_and_event_actor_are_migrated():
    engine, _ = create_database("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE users (
                id VARCHAR(80) NOT NULL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                role VARCHAR(20) NOT NULL,
                CONSTRAINT ck_users_role CHECK (role IN ('employee', 'approver'))
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES ('approver-demo', 'Ava Approver', 'ava@example.test', 'approver')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE claim_events (id TEXT PRIMARY KEY, actor_id VARCHAR(80) NOT NULL REFERENCES users(id), actor_name VARCHAR(120) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO claim_events VALUES ('event-1', 'approver-demo', 'Ava Approver')"
        )

    _migrate_legacy_user_manager_role(engine)

    with engine.connect() as connection:
        manager = connection.exec_driver_sql("SELECT id, name, email, role FROM users").one()
        assert manager == (
            "manager-demo",
            "User Manager",
            "user-manager@example.test",
            "user_manager",
        )
        event = connection.exec_driver_sql(
            "SELECT actor_id, actor_name FROM claim_events WHERE id='event-1'"
        ).one()
        assert event == ("manager-demo", "User Manager")
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()


def test_full_approval_and_paid_lifecycle_and_manager_list(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    mutate(client, claim_id, "submit", 1)
    manager_list = client.get("/api/claims", headers=identity("manager-demo")).json()
    assert [item["id"] for item in manager_list["items"]] == [claim_id]

    approved = mutate(client, claim_id, "approve", 2, user_id="manager-demo", body={})
    assert approved.status_code == 200
    assert approved.json()["approved_amount_paise"] == 12500
    assert approved.json()["status"] == "approved"
    paid = mutate(client, claim_id, "mark-paid", 3, user_id="manager-demo")
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    assert mutate(client, claim_id, "mark-paid", 4, user_id="manager-demo").status_code == 409

    events = detail(client, claim_id)["events"]
    assert [event["action"] for event in events] == ["created", "submitted", "approved", "paid"]
    assert [event["from_status"] for event in events] == [None, "draft", "submitted", "approved"]
    assert [event["to_status"] for event in events] == ["draft", "submitted", "approved", "paid"]
    assert len(events) == 4
    reviewed = client.get("/api/claims", headers=identity("manager-demo")).json()
    assert [item["id"] for item in reviewed["items"]] == [claim_id]


def test_partial_approval_bounds_and_no_event_on_invalid_amount(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    mutate(client, claim_id, "submit", 1)
    for invalid in (0, -1, 12501, 1.5, 9_007_199_254_740_992):
        response = mutate(
            client,
            claim_id,
            "approve",
            2,
            user_id="manager-demo",
            body={"approved_amount_paise": invalid},
        )
        assert_error(response, 422, "validation_error")
    assert len(detail(client, claim_id)["events"]) == 2
    approved = mutate(
        client,
        claim_id,
        "approve",
        2,
        user_id="manager-demo",
        body={"approved_amount_paise": 8000, "comment": "Approved eligible items."},
    )
    assert approved.status_code == 200
    assert approved.json()["approved_amount_paise"] == 8000
    event = detail(client, claim_id)["events"][-1]
    assert event["comment"] == "Approved eligible items."
    assert event["action"] == "approved"


def test_blank_approval_comment_is_recorded_as_null(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    mutate(client, claim_id, "submit", 1)

    approved = mutate(
        client,
        claim_id,
        "approve",
        2,
        user_id="manager-demo",
        body={"comment": "   "},
    )

    assert approved.status_code == 200
    assert detail(client, claim_id)["events"][-1]["comment"] is None


def test_if_match_missing_malformed_and_stale_do_not_write(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    missing = client.post(f"/api/claims/{claim_id}/submit", headers=identity())
    assert_error(missing, 428, "precondition_required")
    malformed = client.post(
        f"/api/claims/{claim_id}/submit",
        headers={**identity(), "If-Match": "1"},
    )
    assert_error(malformed, 422, "invalid_if_match")

    edited = client.patch(
        f"/api/claims/{claim_id}",
        headers={**identity(), "If-Match": '"1"'},
        json={"merchant": "Updated merchant"},
    )
    assert edited.status_code == 200
    stale = client.post(
        f"/api/claims/{claim_id}/submit",
        headers={**identity(), "If-Match": '"1"'},
    )
    assert_error(stale, 412, "stale_version")
    final = detail(client, claim_id)
    assert final["claim"]["version"] == 2
    assert final["claim"]["status"] == "draft"
    assert [event["action"] for event in final["events"]] == ["created", "updated"]


def test_soft_delete_excludes_claim_but_retains_claim_and_event_history(client: TestClient):
    claim = create_claim(client)
    claim_id = claim["id"]
    deleted = client.delete(
        f"/api/claims/{claim_id}",
        headers={**identity(), "If-Match": '"1"'},
    )
    assert deleted.status_code == 200
    assert deleted.headers["etag"] == '"2"'
    assert deleted.json()["deleted_at"] is not None
    assert client.get("/api/claims", headers=identity()).json() == {"items": [], "total": 0}
    archived = detail(client, claim_id)
    assert [event["action"] for event in archived["events"]] == ["created", "deleted"]
    assert archived["events"][-1]["details"] is None
    assert archived["claim"]["id"] == claim_id
    assert archived["claim"]["merchant"] == "Metro Cafe"
    assert archived["claim"]["amount_paise"] == 12500
    assert archived["claim"]["status"] == "draft"
    assert archived["claim"]["deleted_at"] is not None
    assert_error(client.get(f"/api/claims/{claim_id}", headers=identity("manager-demo")), 404, "not_found")
    assert_error(
        client.patch(
            f"/api/claims/{claim_id}",
            headers={**identity(), "If-Match": '"2"'},
            json={"merchant": "Should not change"},
        ),
        409,
        "claim_archived",
    )
    assert len(detail(client, claim_id)["events"]) == 2


def test_event_actor_name_preserves_name_at_event_time(client: TestClient):
    claim = create_claim(client)
    with client.app.state.sessions.begin() as session:
        user = session.get(User, "employee-demo")
        assert user is not None
        user.name = "Updated Employee Name"

    events = detail(client, claim["id"])["events"]
    assert events[0]["actor_id"] == "employee-demo"
    assert events[0]["actor_name"] == "Maya Employee"


def test_list_role_scoping_and_invalid_status(client: TestClient):
    own = create_claim(client)
    other = create_claim(client, user_id="employee-other")
    assert [item["id"] for item in client.get("/api/claims", headers=identity()).json()["items"]] == [
        own["id"]
    ]
    assert [item["id"] for item in client.get("/api/claims", headers=identity("employee-other")).json()["items"]] == [
        other["id"]
    ]
    assert_error(client.get("/api/claims?status=nope", headers=identity()), 422, "validation_error")
    manager = client.get("/api/claims", headers=identity("manager-demo")).json()
    assert manager == {"items": [], "total": 0}


def test_concurrent_review_decisions_only_commit_once(tmp_path):
    application = create_app(f"sqlite:///{tmp_path / 'concurrent.sqlite3'}")
    with TestClient(application) as parallel_client:
        claim = create_claim(parallel_client)
        claim_id = claim["id"]
        submitted = mutate(parallel_client, claim_id, "submit", 1)
        assert submitted.status_code == 200

        barrier = Barrier(2)

        def decide(action: str, body: dict[str, Any]) -> int:
            barrier.wait()
            response = parallel_client.post(
                f"/api/claims/{claim_id}/{action}",
                headers={**identity("manager-demo"), "If-Match": '"2"'},
                json=body,
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    lambda decision: decide(*decision),
                    (("approve", {}), ("reject", {"comment": "Please clarify."})),
                )
            )

        assert sorted(outcomes) == [200, 412]
        result = detail(parallel_client, claim_id)
        assert len(result["events"]) == 3
        assert [event["action"] for event in result["events"]][-1] in {"approved", "rejected"}
        assert result["claim"]["version"] == 3
