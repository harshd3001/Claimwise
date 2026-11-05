from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.models import Claim, ClaimCategory, ClaimEvent, MAX_SAFE_INTEGER, User


class ApiProblem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields or {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def claim_payload(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "employee_id": claim.employee_id,
        "merchant": claim.merchant,
        "category": claim.category,
        "category_id": claim.category_id,
        "receipt_number": claim.receipt_number,
        "description": claim.description,
        "expense_date": claim.expense_date.isoformat(),
        "amount_paise": claim.amount_paise,
        "approved_amount_paise": claim.approved_amount_paise,
        "status": claim.status,
        "version": claim.version,
        "created_at": utc_iso(claim.created_at),
        "updated_at": utc_iso(claim.updated_at),
        "deleted_at": utc_iso(claim.deleted_at),
    }


def event_payload(event: ClaimEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "actor_id": event.actor_id,
        "actor_name": event.actor_name,
        "action": event.action,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "comment": event.comment,
        "details": event.details,
        "created_at": utc_iso(event.created_at),
    }


def _new_event(
    claim: Claim,
    actor: User,
    action: str,
    from_status: str | None,
    to_status: str | None,
    comment: str | None = None,
    details: dict[str, Any] | None = None,
) -> ClaimEvent:
    return ClaimEvent(
        id=str(uuid.uuid4()),
        claim_id=claim.id,
        actor_id=actor.id,
        actor_name=actor.name,
        action=action,
        from_status=from_status,
        to_status=to_status,
        comment=comment,
        details=details,
        created_at=utc_now(),
    )


def _resolve_category(
    session: Session,
    category_name: str,
    category_id: str | None,
    *,
    category_id_was_provided: bool,
    preserved_category_id: str | None = None,
    preserved_category_name: str | None = None,
) -> tuple[str | None, str]:
    if category_id_was_provided:
        if category_id is None:
            return None, category_name
        category = session.get(ClaimCategory, category_id)
        if category is None:
            raise ApiProblem(
                422,
                "validation_error",
                "Request validation failed.",
                {"category_id": "Choose a category from the catalog or enter a custom category."},
            )
        if category.name != category_name and not (
            category.id == preserved_category_id and category_name == preserved_category_name
        ):
            raise ApiProblem(
                422,
                "validation_error",
                "Request validation failed.",
                {"category_id": "The selected category does not match the category name."},
            )
        return category.id, category_name

    category = session.scalar(
        select(ClaimCategory).where(ClaimCategory.name == category_name)
    )
    return (category.id if category else None), category_name


def create_claim(session: Session, actor: User, values: dict[str, Any]) -> Claim:
    if actor.role != "employee":
        raise ApiProblem(403, "forbidden", "Only employees can create claims.")

    category_id, category_name = _resolve_category(
        session,
        values["category"],
        values.get("category_id"),
        category_id_was_provided="category_id" in values,
    )
    now = utc_now()
    claim = Claim(
        id=str(uuid.uuid4()),
        employee_id=actor.id,
        merchant=values["merchant"],
        category=category_name,
        category_id=category_id,
        receipt_number=values.get("receipt_number"),
        description=values["description"],
        expense_date=values["expense_date"],
        amount_paise=values["amount_paise"],
        approved_amount_paise=None,
        status="draft",
        version=1,
        created_at=now,
        updated_at=now,
    )
    with session.begin_nested():
        session.add(claim)
        session.flush()
        session.add(_new_event(claim, actor, "created", None, "draft"))
    return claim


def list_claims(session: Session, actor: User, status: str | None) -> list[Claim]:
    query = select(Claim).where(Claim.deleted_at.is_(None))
    if actor.role == "employee":
        query = query.where(Claim.employee_id == actor.id)
    else:
        previously_acted = exists(
            select(ClaimEvent.id).where(
                ClaimEvent.claim_id == Claim.id,
                ClaimEvent.actor_id == actor.id,
            )
        )
        query = query.where((Claim.status == "submitted") | previously_acted)
    if status is not None:
        query = query.where(Claim.status == status)
    return list(session.scalars(query.order_by(Claim.updated_at.desc(), Claim.id.asc())).all())


def claim_detail(session: Session, actor: User, claim_id: str) -> tuple[Claim, list[ClaimEvent]]:
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise ApiProblem(404, "not_found", "Claim not found.")
    if actor.role == "employee" and claim.employee_id != actor.id:
        raise ApiProblem(404, "not_found", "Claim not found.")
    if claim.deleted_at is not None and (actor.role != "employee" or claim.employee_id != actor.id):
        raise ApiProblem(404, "not_found", "Claim not found.")
    events = list(
        session.scalars(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim.id)
            .order_by(ClaimEvent.created_at.asc(), ClaimEvent.id.asc())
        ).all()
    )
    return claim, events


def mutate_claim(
    session: Session,
    actor: User,
    claim_id: str,
    expected_version: int,
    *,
    action: str,
    allowed_statuses: tuple[str, ...],
    new_status: str | None = None,
    changes: dict[str, Any] | None = None,
    comment: str | None = None,
    approved_amount_paise: int | None = None,
    set_approved_amount: bool = False,
    soft_delete: bool = False,
    owner_only: bool = True,
    required_role: str | None = None,
) -> Claim:
    if required_role is not None and actor.role != required_role:
        role_name = "User Managers" if required_role == "user_manager" else "Employees"
        raise ApiProblem(403, "forbidden", f"Only {role_name} can perform this action.")

    with session.begin_nested():
        claim = session.get(Claim, claim_id)
        if claim is None:
            raise ApiProblem(404, "not_found", "Claim not found.")
        if owner_only and claim.employee_id != actor.id:
            raise ApiProblem(404, "not_found", "Claim not found.")
        if claim.deleted_at is not None:
            raise ApiProblem(409, "claim_archived", "Archived claims are read-only.")
        if claim.version != expected_version:
            raise ApiProblem(412, "stale_version", "The claim changed. Reload it and try again.")
        if claim.status not in allowed_statuses:
            raise ApiProblem(409, "invalid_transition", f"Cannot perform {action} while claim is {claim.status}.")
        from_status = claim.status
        if set_approved_amount:
            if approved_amount_paise is None:
                approved_amount_paise = claim.amount_paise
            if (
                isinstance(approved_amount_paise, bool)
                or not isinstance(approved_amount_paise, int)
                or approved_amount_paise < 1
                or approved_amount_paise > claim.amount_paise
                or approved_amount_paise > MAX_SAFE_INTEGER
            ):
                raise ApiProblem(
                    422,
                    "validation_error",
                    "Request validation failed.",
                    {"approved_amount_paise": "Must be an integer from 1 through amount_paise."},
                )

        updates: dict[str, Any] = {
            "version": claim.version + 1,
            "updated_at": utc_now(),
        }
        if changes and ("category" in changes or "category_id" in changes):
            category_id_was_provided = "category_id" in changes
            if "category" in changes:
                category_name = changes["category"]
            elif changes.get("category_id") is not None:
                selected_category = session.get(ClaimCategory, changes["category_id"])
                category_name = selected_category.name if selected_category else claim.category
            else:
                category_name = claim.category
            category_id, category_name = _resolve_category(
                session,
                category_name,
                changes.get("category_id"),
                category_id_was_provided=category_id_was_provided,
                preserved_category_id=claim.category_id,
                preserved_category_name=claim.category,
            )
            changes["category"] = category_name
            changes["category_id"] = category_id

        details: dict[str, Any] | None = None
        if changes:
            changed_values: dict[str, dict[str, Any]] = {}
            for field, value in changes.items():
                if value is None and field not in {"receipt_number", "category_id"}:
                    raise ApiProblem(
                        422,
                        "validation_error",
                        "Request validation failed.",
                        {field: "This field cannot be null."},
                    )
                previous = getattr(claim, field)
                updates[field] = value
                if previous != value:
                    changed_values[field] = {
                        "before": previous.isoformat() if isinstance(previous, date) else previous,
                        "after": value.isoformat() if isinstance(value, date) else value,
                    }
            details = {"changes": changed_values}
        if new_status is not None:
            updates["status"] = new_status
        if set_approved_amount:
            updates["approved_amount_paise"] = approved_amount_paise
        if soft_delete:
            updates["deleted_at"] = utc_now()

        predicates = [
            Claim.id == claim.id,
            Claim.version == expected_version,
            Claim.status == from_status,
            Claim.deleted_at.is_(None),
        ]
        if owner_only:
            predicates.append(Claim.employee_id == actor.id)
        result = session.execute(update(Claim).where(*predicates).values(**updates))
        if result.rowcount != 1:
            current = session.get(Claim, claim_id)
            if current is None or (owner_only and current.employee_id != actor.id):
                raise ApiProblem(404, "not_found", "Claim not found.")
            if current.version != expected_version:
                raise ApiProblem(412, "stale_version", "The claim changed. Reload it and try again.")
            raise ApiProblem(409, "invalid_transition", "The claim changed and no action was applied.")

        session.flush()
        session.refresh(claim)
        session.add(
            _new_event(
                claim,
                actor,
                "deleted" if soft_delete else action,
                from_status,
                claim.status,
                comment,
                details,
            )
        )
    return claim
