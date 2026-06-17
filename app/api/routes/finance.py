from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_principal
from app.db.session import get_db
from app.schemas.common import APIEnvelope
from app.schemas.finance import (
    AuditEventOut,
    BudgetCreateRequest,
    BudgetOut,
    DashboardOut,
    ExpenseActionRequest,
    ExpenseCategoryOut,
    ExpenseWorkspaceOut,
    PaymentPriorityOut,
    RecurringExpenseCreateRequest,
    RecurringExpenseOut,
    RecurringExpenseRequestCreateRequest,
    RecurringExpenseRequestDecisionRequest,
    RecurringExpenseRequestOut,
    RecurringExpenseUpdateRequest,
    SpendLimitCreateRequest,
    SpendLimitOut,
    SpendLimitUpdateRequest,
    VariableExpenseCreateRequest,
    VariableExpenseOut,
)
from app.services.finance_service import FinanceService

router = APIRouter()
finance_service = FinanceService()


@router.get("/dashboard", response_model=APIEnvelope[DashboardOut])
def dashboard(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[DashboardOut]:
    return APIEnvelope(data=finance_service.build_dashboard(db, principal))


@router.get("/categories", response_model=APIEnvelope[list[ExpenseCategoryOut]])
def categories(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[ExpenseCategoryOut]]:
    return APIEnvelope(
        data=[ExpenseCategoryOut.model_validate(category) for category in finance_service.list_categories(db, principal)]
    )


@router.get("/budgets", response_model=APIEnvelope[list[BudgetOut]])
def budgets(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[BudgetOut]]:
    return APIEnvelope(data=[_to_budget_out(item, finance_service._budget_consumed(item)) for item in finance_service.list_budgets(db, principal)])


@router.post("/budgets", response_model=APIEnvelope[BudgetOut])
def create_budget(
    payload: BudgetCreateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[BudgetOut]:
    budget = finance_service.create_budget(db, principal, payload)
    return APIEnvelope(data=_to_budget_out(budget, finance_service._budget_consumed(budget)))


@router.get("/expenses", response_model=APIEnvelope[ExpenseWorkspaceOut])
def expenses_workspace(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[ExpenseWorkspaceOut]:
    return APIEnvelope(
        data=ExpenseWorkspaceOut(
            recurring_expenses=[_to_recurring_out(item) for item in finance_service.list_recurring_expenses(db, principal)],
            recurring_requests=[_to_recurring_request_out(item) for item in finance_service.list_recurring_requests(db, principal)],
            variable_expenses=[_to_variable_out(item) for item in finance_service.list_variable_expenses(db, principal)],
        )
    )


@router.get("/expenses/variable", response_model=APIEnvelope[list[VariableExpenseOut]])
def variable_expenses(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[VariableExpenseOut]]:
    return APIEnvelope(data=[_to_variable_out(item) for item in finance_service.list_variable_expenses(db, principal)])


@router.post("/expenses/variable", response_model=APIEnvelope[VariableExpenseOut])
def create_variable_expense(
    payload: VariableExpenseCreateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[VariableExpenseOut]:
    return APIEnvelope(data=_to_variable_out(finance_service.create_variable_expense(db, principal, payload)))


@router.post("/expenses/{expense_id}/forward", response_model=APIEnvelope[VariableExpenseOut])
def forward_variable_expense(
    expense_id: str,
    payload: ExpenseActionRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[VariableExpenseOut]:
    return APIEnvelope(data=_to_variable_out(finance_service.review_variable_expense(db, principal, expense_id, payload, "forward")))


@router.post("/expenses/{expense_id}/approve", response_model=APIEnvelope[VariableExpenseOut])
def approve_variable_expense(
    expense_id: str,
    payload: ExpenseActionRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[VariableExpenseOut]:
    return APIEnvelope(data=_to_variable_out(finance_service.review_variable_expense(db, principal, expense_id, payload, "approve")))


@router.post("/expenses/{expense_id}/reject", response_model=APIEnvelope[VariableExpenseOut])
def reject_variable_expense(
    expense_id: str,
    payload: ExpenseActionRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[VariableExpenseOut]:
    return APIEnvelope(data=_to_variable_out(finance_service.review_variable_expense(db, principal, expense_id, payload, "reject")))


@router.post("/expenses/{expense_id}/paid", response_model=APIEnvelope[VariableExpenseOut])
def mark_expense_paid(
    expense_id: str,
    payload: ExpenseActionRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[VariableExpenseOut]:
    return APIEnvelope(data=_to_variable_out(finance_service.review_variable_expense(db, principal, expense_id, payload, "paid")))


@router.get("/recurring-expenses", response_model=APIEnvelope[list[RecurringExpenseOut]])
def recurring_expenses(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[RecurringExpenseOut]]:
    return APIEnvelope(data=[_to_recurring_out(item) for item in finance_service.list_recurring_expenses(db, principal)])


@router.post("/recurring-expenses", response_model=APIEnvelope[RecurringExpenseOut])
def create_recurring_expense(
    payload: RecurringExpenseCreateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[RecurringExpenseOut]:
    return APIEnvelope(data=_to_recurring_out(finance_service.create_recurring_expense(db, principal, payload)))


@router.patch("/recurring-expenses/{recurring_id}", response_model=APIEnvelope[RecurringExpenseOut])
def update_recurring_expense(
    recurring_id: str,
    payload: RecurringExpenseUpdateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[RecurringExpenseOut]:
    return APIEnvelope(data=_to_recurring_out(finance_service.update_recurring_expense(db, principal, recurring_id, payload)))


@router.get("/recurring-expense-requests", response_model=APIEnvelope[list[RecurringExpenseRequestOut]])
def recurring_expense_requests(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[list[RecurringExpenseRequestOut]]:
    return APIEnvelope(data=[_to_recurring_request_out(item) for item in finance_service.list_recurring_requests(db, principal)])


@router.post("/recurring-expense-requests", response_model=APIEnvelope[RecurringExpenseRequestOut])
def create_recurring_expense_request(
    payload: RecurringExpenseRequestCreateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[RecurringExpenseRequestOut]:
    return APIEnvelope(data=_to_recurring_request_out(finance_service.create_recurring_request(db, principal, payload)))


@router.post("/recurring-expense-requests/{request_id}/decision", response_model=APIEnvelope[RecurringExpenseRequestOut])
def decide_recurring_expense_request(
    request_id: str,
    payload: RecurringExpenseRequestDecisionRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[RecurringExpenseRequestOut]:
    return APIEnvelope(data=_to_recurring_request_out(finance_service.decide_recurring_request(db, principal, request_id, payload)))


@router.get("/spend-limits", response_model=APIEnvelope[list[SpendLimitOut]])
def spend_limits(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[SpendLimitOut]]:
    return APIEnvelope(data=[_to_spend_limit_out(item) for item in finance_service.list_spend_limits(db, principal)])


@router.post("/spend-limits", response_model=APIEnvelope[SpendLimitOut])
def create_spend_limit(
    payload: SpendLimitCreateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[SpendLimitOut]:
    return APIEnvelope(data=_to_spend_limit_out(finance_service.create_spend_limit(db, principal, payload)))


@router.patch("/spend-limits/{spend_limit_id}", response_model=APIEnvelope[SpendLimitOut])
def update_spend_limit(
    spend_limit_id: str,
    payload: SpendLimitUpdateRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[SpendLimitOut]:
    return APIEnvelope(data=_to_spend_limit_out(finance_service.update_spend_limit(db, principal, spend_limit_id, payload)))


@router.get("/payment-priorities", response_model=APIEnvelope[list[PaymentPriorityOut]])
def payment_priorities(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[PaymentPriorityOut]]:
    return APIEnvelope(data=[_to_priority_out(item, db, principal) for item in finance_service.recalculate_payment_priorities(db, principal)])


@router.get("/audit-events", response_model=APIEnvelope[list[AuditEventOut]])
def audit_events(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[AuditEventOut]]:
    return APIEnvelope(data=[AuditEventOut.model_validate(item) for item in finance_service.list_audit_events(db, principal)])


def _to_budget_out(budget, spent_amount) -> BudgetOut:
    amount = budget.amount or 0
    return BudgetOut(
        id=budget.id,
        name=budget.name,
        scope=budget.scope,
        currency=budget.currency,
        amount=amount,
        month=budget.month,
        year=budget.year,
        start_date=budget.start_date,
        end_date=budget.end_date,
        alert_threshold_percent=budget.alert_threshold_percent,
        status=budget.status,
        spent_amount=spent_amount,
        remaining_amount=max(amount - spent_amount, Decimal("0")),
        department=budget.department,
        category=budget.category,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


def _to_variable_out(expense) -> VariableExpenseOut:
    return VariableExpenseOut(
        id=expense.id,
        title=expense.title,
        expense_type=expense.expense_type,
        vendor_name=expense.vendor_name,
        currency=expense.currency,
        amount=expense.amount,
        expense_date=expense.expense_date,
        status=expense.status,
        policy_status=expense.policy_status,
        payment_status=expense.payment_status,
        description=expense.description,
        ai_summary=expense.ai_summary,
        ai_risk_level=expense.ai_risk_level,
        rejection_reason=expense.rejection_reason,
        category=expense.category,
        department=expense.department,
        documents=[
            {"id": document.id, "filename": document.filename, "status": document.status, "created_at": document.created_at}
            for document in expense.documents
        ],
        approvals=[item for item in expense.approvals],
        submitted_by_user_id=expense.submitted_by_user_id,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


def _to_recurring_out(item) -> RecurringExpenseOut:
    return RecurringExpenseOut(
        id=item.id,
        name=item.name,
        category=item.category,
        amount=item.amount,
        currency=item.currency,
        billing_cycle=item.billing_cycle,
        due_day=item.due_day,
        next_due_date=item.next_due_date,
        priority=item.priority,
        criticality=item.criticality,
        status=item.status,
        department=item.department,
        vendor=item.vendor,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_recurring_request_out(item) -> RecurringExpenseRequestOut:
    return RecurringExpenseRequestOut(
        id=item.id,
        name=item.name,
        vendor_name=item.vendor_name,
        category=item.category,
        estimated_amount=item.estimated_amount,
        currency=item.currency,
        billing_cycle=item.billing_cycle,
        reason=item.reason,
        status=item.status,
        rejection_reason=item.rejection_reason,
        department=item.department,
        requested_by_user_id=item.requested_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_spend_limit_out(item) -> SpendLimitOut:
    return SpendLimitOut(
        id=item.id,
        category=item.category,
        max_single_expense_amount=item.max_single_expense_amount,
        monthly_limit=item.monthly_limit,
        requires_approval_above_amount=item.requires_approval_above_amount,
        allowed_categories=item.allowed_categories_json or [],
        recurring_creation_restricted=item.recurring_creation_restricted,
        variable_requires_org_owner=item.variable_requires_org_owner,
        active=item.active,
        department=item.department,
        user_id=item.user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_priority_out(item, db: Session, principal) -> PaymentPriorityOut:
    amount = finance_service._priority_amount(db, principal.organization_id, item.expense_type, item.expense_id)
    label = item.expense_type.replace("_", " ").title()
    return PaymentPriorityOut(
        id=item.id,
        expense_type=item.expense_type,
        expense_id=item.expense_id,
        label=label,
        amount=amount,
        priority=item.priority,
        reason=item.reason,
        due_date=item.due_date,
        estimated_cash_out_date=item.estimated_cash_out_date,
    )
