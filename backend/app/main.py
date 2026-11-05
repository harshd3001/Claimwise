"""Claimwise API. Run from backend with `python -m uvicorn app.main:app --reload`."""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import create_database, initialize_database, session_dependency
from app.models import ClaimCategory, User
from app.schemas import (
    ApprovalRequest,
    ClaimCreate,
    ClaimCategoryOut,
    ClaimDetailOut,
    ClaimListOut,
    ClaimOut,
    ClaimPatch,
    ClaimStatus,
    ErrorOut,
    RejectRequest,
    UserOut,
)
from app.service import (
    ApiProblem,
    claim_detail,
    claim_payload,
    create_claim,
    event_payload,
    list_claims,
    mutate_claim,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'claimwise.db').as_posix()}"
IF_MATCH_PATTERN = re.compile(r'^"([1-9][0-9]*)"$')
load_dotenv(BACKEND_DIR / ".env")


def _error_body(code: str, message: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "fields": fields or {}}


def _expected_version(value: str | None) -> int:
    if value is None:
        raise ApiProblem(428, "precondition_required", "If-Match with the current claim version is required.")
    match = IF_MATCH_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ApiProblem(422, "invalid_if_match", 'If-Match must be a quoted positive version, for example "1".')
    return int(match.group(1))


def _field_name(location: tuple[Any, ...]) -> str:
    parts = [str(part) for part in location if part not in ("body", "query", "path", "header")]
    return ".".join(parts) or "request"


def create_app(database_url: str | None = None, seed_sample_data: bool = False) -> FastAPI:
    engine, sessions = create_database(
        database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_database(engine, sessions, seed_sample_data=seed_sample_data)
        yield
        engine.dispose()

    application = FastAPI(title="Claimwise API", version="1.0.0", lifespan=lifespan)
    application.state.engine = engine
    application.state.sessions = sessions

    def get_session(request: Request):
        yield from session_dependency(request.app.state.sessions)

    def current_user(
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-ID"),
        session: Session = Depends(get_session),
    ) -> User:
        if not x_demo_user_id:
            raise ApiProblem(401, "identity_required", "Select a demo user using X-Demo-User-ID.")
        user = session.get(User, x_demo_user_id)
        if user is None:
            raise ApiProblem(401, "invalid_identity", "The selected demo user is not recognized.")
        return user

    @application.exception_handler(ApiProblem)
    async def api_problem_handler(_request: Request, exc: ApiProblem) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.fields),
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for error in exc.errors():
            field = _field_name(tuple(error.get("loc", ())))
            message = str(error.get("msg", "Invalid value."))
            fields[field] = f"{fields[field]}; {message}" if field in fields else message
        return JSONResponse(
            status_code=422,
            content=_error_body("validation_error", "Request validation failed.", fields),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_by_status = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
        }
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code_by_status.get(exc.status_code, "http_error"), message),
            headers=exc.headers,
        )

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/users", response_model=list[UserOut])
    def users(session: Session = Depends(get_session)) -> list[User]:
        return list(session.scalars(select(User).order_by(User.id)).all())

    @application.get("/api/categories", response_model=list[ClaimCategoryOut])
    def categories(session: Session = Depends(get_session)) -> list[ClaimCategory]:
        return list(
            session.scalars(
                select(ClaimCategory).order_by(ClaimCategory.sort_order, ClaimCategory.name)
            ).all()
        )

    @application.get("/api/me", response_model=UserOut)
    def me(actor: User = Depends(current_user)) -> User:
        return actor

    @application.get("/api/claims", response_model=ClaimListOut)
    def claims(
        status: ClaimStatus | None = None,
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        items = [claim_payload(claim) for claim in list_claims(session, actor, status)]
        return {"items": items, "total": len(items)}

    @application.post("/api/claims", response_model=ClaimOut, status_code=201)
    def create(
        body: ClaimCreate,
        response: Response,
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        claim = create_claim(session, actor, body.model_dump(exclude_unset=True))
        response.headers["ETag"] = f'"{claim.version}"'
        return claim_payload(claim)

    @application.get("/api/claims/{claim_id}", response_model=ClaimDetailOut)
    def detail(
        claim_id: str,
        response: Response,
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        claim, events = claim_detail(session, actor, claim_id)
        response.headers["ETag"] = f'"{claim.version}"'
        return {"claim": claim_payload(claim), "events": [event_payload(event) for event in events]}

    def apply(
        claim_id: str,
        if_match: str | None,
        response: Response,
        session: Session,
        actor: User,
        **operation: Any,
    ) -> dict[str, Any]:
        claim = mutate_claim(
            session,
            actor,
            claim_id,
            _expected_version(if_match),
            **operation,
        )
        response.headers["ETag"] = f'"{claim.version}"'
        return claim_payload(claim)

    @application.patch("/api/claims/{claim_id}", response_model=ClaimOut)
    def edit(
        claim_id: str,
        body: ClaimPatch,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="updated",
            allowed_statuses=("draft",),
            changes=body.model_dump(exclude_unset=True),
            required_role="employee",
        )

    @application.delete("/api/claims/{claim_id}", response_model=ClaimOut)
    def delete(
        claim_id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="deleted",
            allowed_statuses=("draft",),
            soft_delete=True,
            required_role="employee",
        )

    @application.post("/api/claims/{claim_id}/submit", response_model=ClaimOut)
    def submit(
        claim_id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="submitted",
            allowed_statuses=("draft",),
            new_status="submitted",
            required_role="employee",
        )

    @application.post("/api/claims/{claim_id}/reopen", response_model=ClaimOut)
    def reopen(
        claim_id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="reopened",
            allowed_statuses=("rejected",),
            new_status="draft",
            required_role="employee",
        )

    @application.post("/api/claims/{claim_id}/approve", response_model=ClaimOut)
    def approve(
        claim_id: str,
        response: Response,
        body: ApprovalRequest | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        approval = body or ApprovalRequest()
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="approved",
            allowed_statuses=("submitted",),
            new_status="approved",
            comment=approval.comment,
            approved_amount_paise=approval.approved_amount_paise,
            set_approved_amount=True,
            owner_only=False,
            required_role="user_manager",
        )

    @application.post("/api/claims/{claim_id}/reject", response_model=ClaimOut)
    def reject(
        claim_id: str,
        response: Response,
        body: RejectRequest | None = None,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="rejected",
            allowed_statuses=("submitted",),
            new_status="rejected",
            comment=body.comment if body else None,
            owner_only=False,
            required_role="user_manager",
        )

    @application.post("/api/claims/{claim_id}/mark-paid", response_model=ClaimOut)
    def mark_paid(
        claim_id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
        session: Session = Depends(get_session),
        actor: User = Depends(current_user),
    ) -> dict[str, Any]:
        return apply(
            claim_id,
            if_match,
            response,
            session,
            actor,
            action="paid",
            allowed_statuses=("approved",),
            new_status="paid",
            owner_only=False,
            required_role="user_manager",
        )

    generated_openapi = application.openapi

    def openapi_with_contract_errors() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema
        schema = generated_openapi()
        schema.setdefault("components", {}).setdefault("schemas", {})["ErrorOut"] = (
            ErrorOut.model_json_schema(ref_template="#/components/schemas/{model}")
        )
        for path, path_item in schema["paths"].items():
            if path in ("/api/health", "/api/users", "/api/categories"):
                continue
            for method, operation in path_item.items():
                if not isinstance(operation, dict) or "responses" not in operation:
                    continue
                statuses = {"401"}
                if path.startswith("/api/claims"):
                    statuses.update({"403", "404"})
                    if method in {"patch", "delete"} or (method == "post" and path != "/api/claims"):
                        statuses.update({"409", "412", "428"})
                if path == "/api/claims" or "requestBody" in operation:
                    statuses.add("422")
                for status in statuses:
                    operation["responses"][status] = {
                        "description": "API error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorOut"}
                            }
                        },
                    }
        application.openapi_schema = schema
        return schema

    application.openapi = openapi_with_contract_errors  # type: ignore[method-assign]

    return application


app = create_app(
    seed_sample_data=os.environ.get("SEED_DEMO_DATA", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)
