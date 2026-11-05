from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Claim, ClaimCategory, ClaimEvent, User


DEFAULT_CATEGORIES = (
    "Meals",
    "Travel",
    "Accommodation",
    "Office supplies",
    "Software & subscriptions",
    "Communication",
    "Training & education",
    "Client entertainment",
    "Other",
)

DEMO_USERS = (
    {"id": "employee-demo", "name": "Maya Employee", "email": "maya@example.test", "role": "employee"},
    {"id": "employee-other", "name": "Arjun Employee", "email": "arjun@example.test", "role": "employee"},
    {"id": "manager-demo", "name": "User Manager", "email": "user-manager@example.test", "role": "user_manager"},
)

DEMO_CLAIMS = (
    {
        "id": "demo-claim-draft",
        "employee_id": "employee-demo",
        "merchant": "Green Leaf Cafe",
        "category": "Meals",
        "description": "Working lunch with the product design team.",
        "expense_date": "2026-11-03",
        "amount_paise": 186500,
        "status": "draft",
        "approved_amount_paise": None,
        "original_description": "Planning session.",
        "events": (
            ("created", None, "draft", None),
            ("updated", "draft", "draft", None),
        ),
    },
    {
        "id": "demo-claim-submitted",
        "employee_id": "employee-demo",
        "merchant": "Metro Rail",
        "category": "Local travel",
        "description": "Travel to the customer workshop at the downtown office.",
        "expense_date": "2026-11-04",
        "amount_paise": 74000,
        "status": "submitted",
        "approved_amount_paise": None,
        "events": (
            ("created", None, "draft", None),
            ("submitted", "draft", "submitted", None),
        ),
    },
    {
        "id": "demo-claim-approved",
        "employee_id": "employee-other",
        "merchant": "Paper & Co.",
        "category": "Office supplies",
        "description": "Notebooks and markers for the quarterly planning session.",
        "expense_date": "2026-11-01",
        "amount_paise": 249900,
        "status": "approved",
        "approved_amount_paise": 249900,
        "events": (
            ("created", None, "draft", None),
            ("submitted", "draft", "submitted", None),
            ("approved", "submitted", "approved", "Receipt and business purpose verified."),
        ),
    },
    {
        "id": "demo-claim-rejected",
        "employee_id": "employee-demo",
        "merchant": "City Taxi",
        "category": "Local travel",
        "description": "Taxi ride after the client site visit.",
        "expense_date": "2026-10-29",
        "amount_paise": 132000,
        "status": "rejected",
        "approved_amount_paise": None,
        "events": (
            ("created", None, "draft", None),
            ("submitted", "draft", "submitted", None),
            ("rejected", "submitted", "rejected", "Please attach the fare receipt and add the client visit reference."),
        ),
    },
    {
        "id": "demo-claim-paid-partial",
        "employee_id": "employee-other",
        "merchant": "Northstar Hotel",
        "category": "Accommodation",
        "description": "One-night stay for the regional customer implementation visit.",
        "expense_date": "2026-10-25",
        "amount_paise": 1285000,
        "status": "paid",
        "approved_amount_paise": 1120000,
        "original_description": "Draft hotel booking.",
        "events": (
            ("created", None, "draft", None),
            ("updated", "draft", "draft", None),
            ("submitted", "draft", "submitted", None),
            ("approved", "submitted", "approved", "Approved eligible room charges; minibar items excluded."),
            ("paid", "approved", "paid", None),
        ),
    },
    {
        "id": "demo-claim-archived",
        "employee_id": "employee-demo",
        "merchant": "Sample Store",
        "category": "Other",
        "description": "Archived sample draft for demonstrating retained history.",
        "expense_date": "2026-10-20",
        "amount_paise": 45900,
        "status": "draft",
        "approved_amount_paise": None,
        "deleted": True,
        "events": (
            ("created", None, "draft", None),
            ("deleted", "draft", "draft", None),
        ),
    },
)


def create_database(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    options: dict[str, object] = {"future": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {
            "check_same_thread": False,
            "timeout": 5,
            "isolation_level": "IMMEDIATE",
        }
        if database_url.endswith(":memory:"):
            options["poolclass"] = StaticPool

    engine = create_engine(database_url, **options)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_database(
    engine: Engine,
    sessions: sessionmaker[Session],
    seed_sample_data: bool = False,
) -> None:
    _migrate_legacy_user_manager_role(engine)
    _migrate_claim_categories(engine)
    ClaimCategory.__table__.create(engine, checkfirst=True)
    with sessions.begin() as session:
        for sort_order, name in enumerate(DEFAULT_CATEGORIES):
            category_id = _category_id(name)
            if session.get(ClaimCategory, category_id) is None:
                session.add(ClaimCategory(id=category_id, name=name, sort_order=sort_order))
    _migrate_claim_category_id(engine)
    Base.metadata.create_all(engine)
    _migrate_claim_receipt_number(engine)
    with sessions.begin() as session:
        for values in DEMO_USERS:
            user = session.get(User, values["id"])
            if user is None:
                session.add(User(**values))
        session.flush()
        if seed_sample_data:
            _seed_demo_claims(session)


def _category_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"claimwise-category:{name}"))


def _migrate_claim_categories(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        table_exists = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='claim_categories'"
        ).scalar_one_or_none()
        if table_exists is None:
            return

        columns = {
            column["name"]
            for column in connection.exec_driver_sql(
                "PRAGMA table_info(claim_categories)"
            ).mappings()
        }
        if "id" in columns:
            return

        rows = connection.exec_driver_sql(
            "SELECT name, sort_order FROM claim_categories ORDER BY sort_order, name"
        ).mappings().all()
        connection.exec_driver_sql(
            """
            CREATE TABLE claim_categories_new (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name VARCHAR(60) NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL
            )
            """
        )
        for row in rows:
            connection.exec_driver_sql(
                """
                INSERT INTO claim_categories_new (id, name, sort_order)
                VALUES (?, ?, ?)
                """,
                (_category_id(row["name"]), row["name"], row["sort_order"]),
            )
        connection.exec_driver_sql("DROP TABLE claim_categories")
        connection.exec_driver_sql(
            "ALTER TABLE claim_categories_new RENAME TO claim_categories"
        )


def _migrate_claim_category_id(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        columns = {
            column["name"]
            for column in connection.exec_driver_sql("PRAGMA table_info(claims)").mappings()
        }
        if not columns or "category_id" in columns:
            return

        connection.exec_driver_sql(
            "ALTER TABLE claims ADD COLUMN category_id VARCHAR(36) "
            "REFERENCES claim_categories(id)"
        )
        connection.exec_driver_sql(
            """
            UPDATE claims
            SET category_id = (
                SELECT claim_categories.id
                FROM claim_categories
                WHERE claim_categories.name = claims.category
            )
            """
        )


def _migrate_claim_receipt_number(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        columns = {
            column["name"]
            for column in connection.exec_driver_sql("PRAGMA table_info(claims)").mappings()
        }
        if columns and "receipt_number" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE claims ADD COLUMN receipt_number VARCHAR(120)"
            )


def _migrate_legacy_user_manager_role(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    connection = engine.raw_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        row = cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if row is None:
            return
        schema = row[0] or ""
        if not any(role in schema for role in ("'approver'", "'manager'")):
            return

        connection.commit()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            CREATE TABLE users_new (
                id VARCHAR(80) NOT NULL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                role VARCHAR(20) NOT NULL,
                CONSTRAINT ck_users_role CHECK (role IN ('employee', 'user_manager'))
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO users_new (id, name, email, role)
            SELECT
                CASE WHEN id = 'approver-demo' THEN 'manager-demo' ELSE id END,
                CASE WHEN role IN ('approver', 'manager') THEN 'User Manager' ELSE name END,
                CASE WHEN id = 'approver-demo' THEN 'user-manager@example.test' ELSE email END,
                CASE WHEN role IN ('approver', 'manager') THEN 'user_manager' ELSE role END
            FROM users
            """
        )
        events_exist = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='claim_events'"
        ).fetchone()
        if events_exist:
            cursor.execute(
                """
                UPDATE claim_events
                SET actor_id='manager-demo', actor_name='User Manager'
                WHERE actor_id IN ('approver-demo', 'manager-demo')
                """
            )
        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_new RENAME TO users")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        connection.close()


def _seed_demo_claims(session: Session) -> None:
    now = datetime.now(timezone.utc)
    sample_ids = [claim["id"] for claim in DEMO_CLAIMS]
    existing_ids = set(
        session.scalars(select(Claim.id).where(Claim.id.in_(sample_ids))).all()
    )
    for index, values in enumerate(DEMO_CLAIMS):
        if values["id"] in existing_ids:
            continue

        created_at = now - timedelta(days=1, minutes=index * 4)
        claim = Claim(
            id=values["id"],
            employee_id=values["employee_id"],
            merchant=values["merchant"],
            category=values["category"],
            category_id=session.scalar(
                select(ClaimCategory.id).where(ClaimCategory.name == values["category"])
            ),
            description=values["description"],
            expense_date=datetime.strptime(values["expense_date"], "%Y-%m-%d").date(),
            amount_paise=values["amount_paise"],
            approved_amount_paise=values["approved_amount_paise"],
            status=values["status"],
            version=len(values["events"]),
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=len(values["events"])),
            deleted_at=created_at + timedelta(minutes=len(values["events"])) if values.get("deleted") else None,
        )
        session.add(claim)
        session.flush()

        for event_index, (action, from_status, to_status, comment) in enumerate(values["events"]):
            actor_id = (
                "manager-demo"
                if action in {"approved", "rejected", "paid"}
                else values["employee_id"]
            )
            details = None
            if action == "updated":
                details = {
                    "changes": {
                        "description": {
                            "before": values["original_description"],
                            "after": values["description"],
                        }
                    }
                }
            actor = session.get(User, actor_id)
            session.add(
                ClaimEvent(
                    id=f"{claim.id}-event-{event_index + 1}",
                    claim_id=claim.id,
                    actor_id=actor_id,
                    actor_name=actor.name if actor else actor_id,
                    action=action,
                    from_status=from_status,
                    to_status=to_status,
                    comment=comment,
                    details=details,
                    created_at=created_at + timedelta(minutes=event_index),
                )
            )


def session_dependency(sessions: sessionmaker[Session]) -> Iterator[Session]:
    session = sessions()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
