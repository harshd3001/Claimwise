from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import MAX_SAFE_INTEGER


ClaimStatus = Literal["draft", "submitted", "approved", "rejected", "paid"]
ClaimAction = Literal["created", "updated", "submitted", "reopened", "approved", "rejected", "deleted", "paid"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _trim_required_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("A non-empty string is required.")
    value = value.strip()
    if not value:
        raise ValueError("This field must not be blank.")
    return value


def _iso_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError("Use a date in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Enter a valid calendar date.") from exc


class ClaimCreate(StrictModel):
    merchant: str = Field(max_length=120)
    category: str = Field(max_length=60)
    receipt_number: str | None = Field(default=None, max_length=120)
    description: str = Field(max_length=1000)
    expense_date: date
    amount_paise: int = Field(strict=True, gt=0, le=MAX_SAFE_INTEGER)

    @field_validator("merchant", "category", "description", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> str:
        return _trim_required_text(value)

    @field_validator("receipt_number", mode="before")
    @classmethod
    def trim_optional_receipt_number(cls, value: Any) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("expense_date", mode="before")
    @classmethod
    def parse_date(cls, value: Any) -> date:
        return _iso_date(value)


class ClaimPatch(StrictModel):
    merchant: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    receipt_number: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    expense_date: date | None = None
    amount_paise: int | None = Field(default=None, strict=True, gt=0, le=MAX_SAFE_INTEGER)

    @field_validator("merchant", "category", "description", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> str:
        return _trim_required_text(value)

    @field_validator("receipt_number", mode="before")
    @classmethod
    def trim_optional_receipt_number(cls, value: Any) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("expense_date", mode="before")
    @classmethod
    def parse_date(cls, value: Any) -> date:
        return _iso_date(value)

    @model_validator(mode="after")
    def has_editable_fields(self) -> "ClaimPatch":
        if not self.model_fields_set:
            raise ValueError("At least one editable field is required.")
        return self


class ApprovalRequest(StrictModel):
    approved_amount_paise: int | None = Field(default=None, strict=True, gt=0, le=MAX_SAFE_INTEGER)
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def trim_optional_comment(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class RejectRequest(StrictModel):
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def trim_optional_comment(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["employee", "user_manager"]


class ClaimOut(BaseModel):
    id: str
    employee_id: str
    merchant: str
    category: str
    receipt_number: str | None
    description: str
    expense_date: date
    amount_paise: int
    approved_amount_paise: int | None
    status: ClaimStatus
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ClaimEventOut(BaseModel):
    id: str
    actor_id: str
    actor_name: str
    action: ClaimAction
    from_status: ClaimStatus | None
    to_status: ClaimStatus | None
    comment: str | None
    details: dict[str, Any] | None
    created_at: datetime


class ClaimListOut(BaseModel):
    items: list[ClaimOut]
    total: int


class ClaimDetailOut(BaseModel):
    claim: ClaimOut
    events: list[ClaimEventOut]


class ErrorOut(BaseModel):
    code: str
    message: str
    fields: dict[str, str] = Field(default_factory=dict)
