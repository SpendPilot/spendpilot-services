from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    default_currency: Mapped[str] = mapped_column(String(10), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="organization")
    departments: Mapped[list["Department"]] = relationship(back_populates="organization")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="organization")
    categories: Mapped[list["ExpenseCategory"]] = relationship(back_populates="organization")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="organization")
    documents: Mapped[list["Document"]] = relationship(back_populates="organization")
    vendors: Mapped[list["Vendor"]] = relationship(back_populates="organization")
    recurring_expenses: Mapped[list["RecurringExpense"]] = relationship(back_populates="organization")
    recurring_expense_requests: Mapped[list["RecurringExpenseRequest"]] = relationship(back_populates="organization")
    spend_limits: Mapped[list["SpendLimit"]] = relationship(back_populates="organization")
    payment_priorities: Mapped[list["PaymentPriority"]] = relationship(back_populates="organization")
    ai_chat_sessions: Mapped[list["AIChatSession"]] = relationship(back_populates="organization")
    ai_chat_messages: Mapped[list["AIChatMessage"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    entra_oid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    platform_role: Mapped[str] = mapped_column(String(30), default="employee")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="user")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")
    owned_documents: Mapped[list["Document"]] = relationship(
        back_populates="owner",
        foreign_keys=lambda: [Document.owner_user_id],
    )
    submitted_expenses: Mapped[list["Expense"]] = relationship(
        back_populates="submitted_by",
        foreign_keys=lambda: [Expense.submitted_by_user_id],
    )
    reviewed_department_expenses: Mapped[list["Expense"]] = relationship(
        foreign_keys=lambda: [Expense.dept_head_reviewer_user_id],
    )
    approved_org_expenses: Mapped[list["Expense"]] = relationship(
        foreign_keys=lambda: [Expense.org_owner_approver_user_id],
    )
    recurring_expenses_created: Mapped[list["RecurringExpense"]] = relationship(
        foreign_keys=lambda: [RecurringExpense.created_by_user_id],
    )
    recurring_expense_requests_created: Mapped[list["RecurringExpenseRequest"]] = relationship(
        foreign_keys=lambda: [RecurringExpenseRequest.requested_by_user_id],
    )
    chat_sessions: Mapped[list["AIChatSession"]] = relationship(back_populates="user")


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_department_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="departments")
    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="department")


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_membership"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(30), default="employee")
    status: Mapped[str] = mapped_column(String(20), default="active")
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    department: Mapped[Department | None] = relationship(back_populates="memberships")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_fingerprint: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    session_identifier: Mapped[str] = mapped_column(String(255), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    auth_provider: Mapped[str] = mapped_column(String(30), default="entra")
    user_agent: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    claims_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="sessions")
    organization: Mapped[Organization] = relationship()


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_category_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="categories")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="category")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="category")


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("expense_categories.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(20), default="company")
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date())
    end_date: Mapped[date] = mapped_column(Date())
    alert_threshold_percent: Mapped[int] = mapped_column(Integer, default=80)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="budgets")
    department: Mapped[Department | None] = relationship()
    category: Mapped[ExpenseCategory | None] = relationship(back_populates="budgets")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="budget")


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_vendor_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    criticality: Mapped[str] = mapped_column(String(20), default="medium")
    contact_info: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="vendors")
    recurring_expenses: Mapped[list["RecurringExpense"]] = relationship(back_populates="vendor")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="vendor")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    submitted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    budget_id: Mapped[str | None] = mapped_column(ForeignKey("budgets.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("expense_categories.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    expense_type: Mapped[str] = mapped_column(String(20), default="variable")
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expense_date: Mapped[date] = mapped_column(Date())
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    policy_status: Mapped[str] = mapped_column(String(30), default="needs_review")
    dept_head_reviewer_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    org_owner_approver_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    ai_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="expenses")
    submitted_by: Mapped[User] = relationship(
        back_populates="submitted_expenses",
        foreign_keys=[submitted_by_user_id],
    )
    org_owner_approver: Mapped[User | None] = relationship(
        foreign_keys=[org_owner_approver_user_id],
        overlaps="approved_org_expenses",
    )
    dept_head_reviewer: Mapped[User | None] = relationship(
        foreign_keys=[dept_head_reviewer_user_id],
        overlaps="reviewed_department_expenses",
    )
    department: Mapped[Department | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship(back_populates="expenses")
    budget: Mapped[Budget | None] = relationship(back_populates="expenses")
    category: Mapped[ExpenseCategory | None] = relationship(back_populates="expenses")
    approvals: Mapped[list["ExpenseApproval"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by=lambda: ExpenseApproval.created_at.desc(),
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="expense")


class ExpenseApproval(Base):
    __tablename__ = "expense_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    expense_id: Mapped[str] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"), index=True)
    approver_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    expense: Mapped[Expense] = relationship(back_populates="approvals")
    approver: Mapped[User] = relationship()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    expense_id: Mapped[str | None] = mapped_column(ForeignKey("expenses.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    storage_kind: Mapped[str] = mapped_column(String(20), default="local")
    storage_path: Mapped[str] = mapped_column(String(1024))
    storage_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    linked_expense_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    linked_expense_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    extracted_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="documents")
    owner: Mapped[User] = relationship(back_populates="owned_documents")
    department: Mapped[Department | None] = relationship()
    expense: Mapped[Expense | None] = relationship(back_populates="documents")
    scans: Mapped[list["DocumentScan"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by=lambda: DocumentScan.created_at.desc(),
    )


class DocumentScan(Base):
    __tablename__ = "document_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text())
    findings_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    recommendations_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    provider_status: Mapped[str] = mapped_column(String(50))
    raw_response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="scans")
    requested_by: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(50))
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship()
    actor: Mapped[User | None] = relationship()


class RecurringExpense(Base):
    __tablename__ = "recurring_expenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"), nullable=True, index=True)
    bill_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    billing_cycle: Mapped[str] = mapped_column(String(30), default="monthly")
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="pay_this_week")
    criticality: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="recurring_expenses")
    department: Mapped[Department | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship(back_populates="recurring_expenses")
    bill_document: Mapped[Document | None] = relationship()
    created_by: Mapped[User] = relationship(
        foreign_keys=[created_by_user_id],
        overlaps="recurring_expenses_created",
    )


class RecurringExpenseRequest(Base):
    __tablename__ = "recurring_expense_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100))
    estimated_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    billing_cycle: Mapped[str] = mapped_column(String(30), default="monthly")
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    bill_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="recurring_expense_requests")
    department: Mapped[Department] = relationship()
    requested_by: Mapped[User] = relationship(
        foreign_keys=[requested_by_user_id],
        overlaps="recurring_expense_requests_created",
    )
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_user_id])
    bill_document: Mapped[Document | None] = relationship()


class SpendLimit(Base):
    __tablename__ = "spend_limits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_single_expense_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    requires_approval_above_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    allowed_categories_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    recurring_creation_restricted: Mapped[bool] = mapped_column(default=False)
    variable_requires_org_owner: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="spend_limits")
    department: Mapped[Department | None] = relationship()


class PaymentPriority(Base):
    __tablename__ = "payment_priorities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    expense_type: Mapped[str] = mapped_column(String(20))
    expense_id: Mapped[str] = mapped_column(String(36), index=True)
    priority: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text())
    due_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    estimated_cash_out_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="payment_priorities")


class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="ai_chat_sessions")
    user: Mapped[User] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["AIChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by=lambda: AIChatMessage.created_at.asc(),
    )


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text())
    grounded_context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="ai_chat_messages")
    session: Mapped[AIChatSession] = relationship(back_populates="messages")
