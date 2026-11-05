from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


MAX_SAFE_INTEGER = 9_007_199_254_740_991


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (CheckConstraint("role IN ('employee', 'user_manager')", name="ck_users_role"),)


class ClaimCategory(Base):
    __tablename__ = "claim_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    merchant: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("claim_categories.id"), nullable=True
    )
    receipt_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_amount_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[User] = relationship()
    category_record: Mapped[ClaimCategory | None] = relationship()
    events: Mapped[list[ClaimEvent]] = relationship(
        back_populates="claim", order_by="(ClaimEvent.created_at, ClaimEvent.id)"
    )

    __table_args__ = (
        CheckConstraint(
            f"amount_paise > 0 AND amount_paise <= {MAX_SAFE_INTEGER}",
            name="ck_claims_amount_range",
        ),
        CheckConstraint(
            f"approved_amount_paise IS NULL OR "
            f"(approved_amount_paise > 0 AND approved_amount_paise <= amount_paise "
            f"AND approved_amount_paise <= {MAX_SAFE_INTEGER})",
            name="ck_claims_approved_amount_range",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'rejected', 'paid')",
            name="ck_claims_status",
        ),
        CheckConstraint("version > 0", name="ck_claims_version_positive"),
        Index("ix_claims_employee_status", "employee_id", "status"),
        Index("ix_claims_category_id", "category_id"),
    )


class ClaimEvent(Base):
    __tablename__ = "claim_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    claim: Mapped[Claim] = relationship(back_populates="events")
    actor: Mapped[User] = relationship()

    __table_args__ = (Index("ix_claim_events_claim_created_id", "claim_id", "created_at", "id"),)
