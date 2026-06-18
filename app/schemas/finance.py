from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ExpenseCategoryOut(BaseModel):
    id: str
    code: str
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class DepartmentSummaryOut(BaseModel):
    id: str
    name: str

    model_config = {"from_attributes": True}


class VendorOut(BaseModel):
    id: str
    name: str
    category: str | None = None
    criticality: str

    model_config = {"from_attributes": True}


class BudgetCreateRequest(BaseModel):
    name: str
    scope: str = "company"
    department_id: str | None = None
    category_id: str | None = None
    currency: str = "INR"
    amount: Decimal
    month: int
    year: int
    alert_threshold_percent: int = 80


class BudgetOut(BaseModel):
    id: str
    name: str
    scope: str
    currency: str
    amount: Decimal
    month: int | None = None
    year: int | None = None
    start_date: date
    end_date: date
    alert_threshold_percent: int
    status: str
    spent_amount: Decimal = Decimal("0")
    remaining_amount: Decimal = Decimal("0")
    department: DepartmentSummaryOut | None = None
    category: ExpenseCategoryOut | None = None
    created_at: datetime
    updated_at: datetime


class BudgetSummaryOut(BaseModel):
    company_budget: Decimal
    company_used: Decimal
    company_remaining: Decimal
    department_budgets: list[BudgetOut] = Field(default_factory=list)


class ExpenseApprovalOut(BaseModel):
    id: str
    approver_user_id: str
    action: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VariableExpenseCreateRequest(BaseModel):
    title: str
    category_id: str | None = None
    vendor_name: str | None = None
    amount: Decimal
    expense_date: date
    description: str | None = None
    document_id: str | None = None
    currency: str = "INR"


class ExpenseActionRequest(BaseModel):
    comment: str | None = None
    rejection_reason: str | None = None


class ExpenseDocumentOut(BaseModel):
    id: str
    filename: str
    status: str
    created_at: datetime


class VariableExpenseOut(BaseModel):
    id: str
    title: str
    expense_type: str
    vendor_name: str | None
    currency: str
    amount: Decimal
    expense_date: date
    status: str
    policy_status: str
    payment_status: str
    description: str | None
    ai_summary: str | None
    ai_risk_level: str | None
    rejection_reason: str | None
    category: ExpenseCategoryOut | None
    department: DepartmentSummaryOut | None
    documents: list[ExpenseDocumentOut] = Field(default_factory=list)
    approvals: list[ExpenseApprovalOut] = Field(default_factory=list)
    submitted_by_user_id: str
    created_at: datetime
    updated_at: datetime


class RecurringExpenseCreateRequest(BaseModel):
    name: str
    category: str
    vendor_name: str | None = None
    amount: Decimal
    currency: str = "INR"
    billing_cycle: str = "monthly"
    due_day: int | None = None
    next_due_date: date | None = None
    priority: str = "pay_this_week"
    criticality: str = "medium"
    department_id: str | None = None
    bill_document_id: str | None = None


class RecurringExpenseUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    vendor_name: str | None = None
    amount: Decimal | None = None
    billing_cycle: str | None = None
    due_day: int | None = None
    next_due_date: date | None = None
    priority: str | None = None
    criticality: str | None = None
    status: str | None = None
    department_id: str | None = None


class RecurringExpenseRequestCreateRequest(BaseModel):
    name: str
    category: str
    vendor_name: str
    estimated_amount: Decimal
    currency: str = "INR"
    billing_cycle: str = "monthly"
    reason: str | None = None
    bill_document_id: str | None = None


class RecurringExpenseRequestDecisionRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None


class RecurringExpenseOut(BaseModel):
    id: str
    name: str
    category: str
    amount: Decimal
    currency: str
    billing_cycle: str
    due_day: int | None
    next_due_date: date | None
    priority: str
    criticality: str
    status: str
    department: DepartmentSummaryOut | None = None
    vendor: VendorOut | None = None
    created_at: datetime
    updated_at: datetime


class RecurringExpenseRequestOut(BaseModel):
    id: str
    name: str
    vendor_name: str
    category: str
    estimated_amount: Decimal
    currency: str
    billing_cycle: str
    reason: str | None
    status: str
    rejection_reason: str | None
    department: DepartmentSummaryOut
    requested_by_user_id: str
    created_at: datetime
    updated_at: datetime


class SpendLimitCreateRequest(BaseModel):
    department_id: str | None = None
    category: str | None = None
    max_single_expense_amount: Decimal | None = None
    monthly_limit: Decimal | None = None
    requires_approval_above_amount: Decimal | None = None
    recurring_creation_restricted: bool = False
    variable_requires_org_owner: bool = False
    active: bool = True


class SpendLimitUpdateRequest(BaseModel):
    department_id: str | None = None
    category: str | None = None
    max_single_expense_amount: Decimal | None = None
    monthly_limit: Decimal | None = None
    requires_approval_above_amount: Decimal | None = None
    recurring_creation_restricted: bool | None = None
    variable_requires_org_owner: bool | None = None
    active: bool | None = None


class SpendLimitOut(BaseModel):
    id: str
    category: str | None
    max_single_expense_amount: Decimal | None
    monthly_limit: Decimal | None
    requires_approval_above_amount: Decimal | None
    recurring_creation_restricted: bool
    variable_requires_org_owner: bool
    active: bool
    department: DepartmentSummaryOut | None = None
    created_at: datetime
    updated_at: datetime


class PaymentPriorityOut(BaseModel):
    id: str
    expense_type: str
    expense_id: str
    label: str
    amount: Decimal
    priority: str
    reason: str
    due_date: date | None
    estimated_cash_out_date: date | None


class CategorySpendOut(BaseModel):
    category: str
    amount: Decimal


class DepartmentSpendOut(BaseModel):
    department: str
    amount: Decimal


class DashboardOut(BaseModel):
    organization_name: str
    role: str
    total_spend_this_month: Decimal
    recurring_spend_this_month: Decimal
    variable_spend_this_month: Decimal
    pending_approvals: int
    approved_expenses: int
    rejected_expenses: int
    company_budget_used: Decimal
    company_budget_remaining: Decimal
    upcoming_payment_count: int
    cash_outflow_this_week: Decimal
    cash_outflow_this_month: Decimal
    budgets: list[BudgetOut] = Field(default_factory=list)
    category_breakdown: list[CategorySpendOut] = Field(default_factory=list)
    department_breakdown: list[DepartmentSpendOut] = Field(default_factory=list)
    payment_priorities: list[PaymentPriorityOut] = Field(default_factory=list)


class ExpenseWorkspaceOut(BaseModel):
    recurring_expenses: list[RecurringExpenseOut] = Field(default_factory=list)
    recurring_requests: list[RecurringExpenseRequestOut] = Field(default_factory=list)
    variable_expenses: list[VariableExpenseOut] = Field(default_factory=list)


class AuditEventOut(BaseModel):
    id: str
    resource_type: str
    resource_id: str
    action: str
    details_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
