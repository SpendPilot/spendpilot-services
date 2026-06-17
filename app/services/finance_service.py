from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.rbac import ROLE_DEPT_HEAD, ROLE_EMPLOYEE, ROLE_ORG_OWNER
from app.core.security import AuthenticatedPrincipal
from app.models import (
    AuditEvent,
    Budget,
    Department,
    Document,
    Expense,
    ExpenseApproval,
    ExpenseCategory,
    PaymentPriority,
    RecurringExpense,
    RecurringExpenseRequest,
    SpendLimit,
    Vendor,
)
from app.schemas.finance import (
    BudgetCreateRequest,
    BudgetOut,
    CategorySpendOut,
    DashboardOut,
    DepartmentSpendOut,
    ExpenseActionRequest,
    PaymentPriorityOut,
    RecurringExpenseCreateRequest,
    RecurringExpenseRequestCreateRequest,
    RecurringExpenseRequestDecisionRequest,
    RecurringExpenseUpdateRequest,
    SpendLimitCreateRequest,
    SpendLimitUpdateRequest,
    VariableExpenseCreateRequest,
)
from app.services.audit_service import create_audit_event


class FinanceService:
    def list_categories(self, db: Session, principal: AuthenticatedPrincipal) -> list[ExpenseCategory]:
        return (
            db.query(ExpenseCategory)
            .filter(ExpenseCategory.organization_id == principal.organization_id)
            .order_by(ExpenseCategory.name.asc())
            .all()
        )

    def list_budgets(self, db: Session, principal: AuthenticatedPrincipal) -> list[Budget]:
        query = (
            db.query(Budget)
            .options(joinedload(Budget.category), joinedload(Budget.department), joinedload(Budget.expenses))
            .filter(Budget.organization_id == principal.organization_id)
            .order_by(Budget.year.desc().nullslast(), Budget.month.desc().nullslast(), Budget.name.asc())
        )
        if principal.role in {ROLE_EMPLOYEE, ROLE_DEPT_HEAD} and principal.department_id:
            query = query.filter((Budget.scope == "company") | (Budget.department_id == principal.department_id))
        elif principal.role in {ROLE_EMPLOYEE, ROLE_DEPT_HEAD}:
            query = query.filter(Budget.scope == "company")
        return query.all()

    def create_budget(self, db: Session, principal: AuthenticatedPrincipal, payload: BudgetCreateRequest) -> Budget:
        self._require_org_owner(principal)
        department_id = self._validate_department(db, principal, payload.department_id) if payload.department_id else None
        category_id = self._validate_category(db, principal, payload.category_id) if payload.category_id else None
        start_date = date(payload.year, payload.month, 1)
        end_date = date(payload.year, payload.month, monthrange(payload.year, payload.month)[1])
        budget = Budget(
            organization_id=principal.organization_id,
            department_id=department_id,
            category_id=category_id,
            name=payload.name,
            scope=payload.scope,
            currency=payload.currency,
            amount=payload.amount,
            month=payload.month,
            year=payload.year,
            start_date=start_date,
            end_date=end_date,
            alert_threshold_percent=payload.alert_threshold_percent,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="budget",
            resource_id=budget.id,
            action="created",
            details={"name": budget.name, "scope": budget.scope, "amount": str(budget.amount)},
        )
        return budget

    def list_variable_expenses(self, db: Session, principal: AuthenticatedPrincipal) -> list[Expense]:
        query = (
            db.query(Expense)
            .options(
                joinedload(Expense.category),
                joinedload(Expense.department),
                joinedload(Expense.documents),
                joinedload(Expense.approvals),
            )
            .filter(
                Expense.organization_id == principal.organization_id,
                Expense.expense_type == "variable",
            )
            .order_by(Expense.created_at.desc())
        )
        if principal.role == ROLE_DEPT_HEAD:
            query = query.filter(Expense.department_id == principal.department_id)
        elif principal.role == ROLE_EMPLOYEE:
            query = query.filter(Expense.submitted_by_user_id == principal.user_id)
        return query.all()

    def get_variable_expense(self, db: Session, principal: AuthenticatedPrincipal, expense_id: str) -> Expense:
        expense = (
            db.query(Expense)
            .options(
                joinedload(Expense.category),
                joinedload(Expense.department),
                joinedload(Expense.documents),
                joinedload(Expense.approvals),
            )
            .filter(
                Expense.id == expense_id,
                Expense.organization_id == principal.organization_id,
                Expense.expense_type == "variable",
            )
            .first()
        )
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variable expense not found")
        self._assert_expense_access(principal, expense)
        return expense

    def create_variable_expense(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        payload: VariableExpenseCreateRequest,
    ) -> Expense:
        if principal.role == ROLE_ORG_OWNER:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use recurring or admin workflows for owner-managed payments")
        if not principal.department_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department onboarding is required")

        category = self._get_category(db, principal.organization_id, payload.category_id) if payload.category_id else None
        spend_limit = self._evaluate_spend_limits(db, principal, payload.amount, category.name if category else None)
        status_value = "forwarded_to_org_owner" if principal.role == ROLE_DEPT_HEAD else "pending_dept_head"
        policy_status = "needs_org_owner_review" if principal.role == ROLE_DEPT_HEAD else "needs_dept_head_review"
        if spend_limit and spend_limit.variable_requires_org_owner:
            status_value = "forwarded_to_org_owner"
            policy_status = "needs_org_owner_review"

        expense = Expense(
            organization_id=principal.organization_id,
            submitted_by_user_id=principal.user_id,
            department_id=principal.department_id,
            category_id=category.id if category else None,
            vendor_id=self._find_or_create_vendor(db, principal.organization_id, payload.vendor_name, category.name if category else None),
            title=payload.title,
            expense_type="variable",
            vendor_name=payload.vendor_name,
            currency=payload.currency,
            amount=payload.amount,
            expense_date=payload.expense_date,
            description=payload.description,
            status=status_value,
            policy_status=policy_status,
        )
        db.add(expense)
        db.flush()
        if payload.document_id:
            document = self._get_document(db, principal.organization_id, payload.document_id)
            document.expense_id = expense.id
            document.department_id = principal.department_id
            document.linked_expense_type = "variable_expense"
            document.linked_expense_id = expense.id
        db.commit()
        db.refresh(expense)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="variable_expense",
            resource_id=expense.id,
            action="created",
            details={"title": expense.title, "amount": str(expense.amount), "status": expense.status},
        )
        return expense

    def review_variable_expense(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        expense_id: str,
        payload: ExpenseActionRequest,
        action: str,
    ) -> Expense:
        expense = self.get_variable_expense(db, principal, expense_id)
        if principal.role == ROLE_DEPT_HEAD:
            if expense.department_id != principal.department_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Department access denied")
            if action == "forward":
                expense.status = "forwarded_to_org_owner"
                expense.policy_status = "needs_org_owner_review"
                expense.dept_head_reviewer_user_id = principal.user_id
            elif action == "reject":
                expense.status = "rejected_by_dept_head"
                expense.policy_status = "rejected"
                expense.dept_head_reviewer_user_id = principal.user_id
                expense.rejection_reason = payload.rejection_reason or payload.comment
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported department action")
        elif principal.role == ROLE_ORG_OWNER:
            if action == "approve":
                expense.status = "approved_by_org_owner"
                expense.policy_status = "approved"
                expense.org_owner_approver_user_id = principal.user_id
            elif action == "reject":
                expense.status = "rejected_by_org_owner"
                expense.policy_status = "rejected"
                expense.org_owner_approver_user_id = principal.user_id
                expense.rejection_reason = payload.rejection_reason or payload.comment
            elif action == "paid":
                expense.status = "paid"
                expense.payment_status = "paid"
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported owner action")
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

        approval = ExpenseApproval(
            expense_id=expense.id,
            approver_user_id=principal.user_id,
            action=action,
            comment=payload.comment or payload.rejection_reason,
        )
        db.add(approval)
        db.commit()
        db.refresh(expense)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="variable_expense",
            resource_id=expense.id,
            action=action,
            details={"status": expense.status},
        )
        return expense

    def list_recurring_expenses(self, db: Session, principal: AuthenticatedPrincipal) -> list[RecurringExpense]:
        query = (
            db.query(RecurringExpense)
            .options(joinedload(RecurringExpense.department), joinedload(RecurringExpense.vendor))
            .filter(RecurringExpense.organization_id == principal.organization_id)
            .order_by(RecurringExpense.next_due_date.asc().nullslast(), RecurringExpense.name.asc())
        )
        if principal.role == ROLE_DEPT_HEAD:
            query = query.filter((RecurringExpense.department_id == principal.department_id) | (RecurringExpense.department_id.is_(None)))
        elif principal.role == ROLE_EMPLOYEE:
            query = query.filter(RecurringExpense.department_id == principal.department_id)
        return query.all()

    def create_recurring_expense(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        payload: RecurringExpenseCreateRequest,
    ) -> RecurringExpense:
        self._require_org_owner(principal)
        department_id = self._validate_department(db, principal, payload.department_id) if payload.department_id else None
        recurring = RecurringExpense(
            organization_id=principal.organization_id,
            department_id=department_id,
            vendor_id=self._find_or_create_vendor(db, principal.organization_id, payload.vendor_name, payload.category),
            bill_document_id=payload.bill_document_id,
            name=payload.name,
            category=payload.category,
            amount=payload.amount,
            currency=payload.currency,
            billing_cycle=payload.billing_cycle,
            due_day=payload.due_day,
            next_due_date=payload.next_due_date,
            priority=payload.priority,
            criticality=payload.criticality,
            created_by_user_id=principal.user_id,
        )
        db.add(recurring)
        db.commit()
        db.refresh(recurring)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="recurring_expense",
            resource_id=recurring.id,
            action="created",
            details={"name": recurring.name, "amount": str(recurring.amount)},
        )
        return recurring

    def update_recurring_expense(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        recurring_id: str,
        payload: RecurringExpenseUpdateRequest,
    ) -> RecurringExpense:
        self._require_org_owner(principal)
        recurring = (
            db.query(RecurringExpense)
            .options(joinedload(RecurringExpense.department), joinedload(RecurringExpense.vendor))
            .filter(
                RecurringExpense.id == recurring_id,
                RecurringExpense.organization_id == principal.organization_id,
            )
            .first()
        )
        if recurring is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring expense not found")
        updates = payload.model_dump(exclude_unset=True)
        vendor_name = updates.pop("vendor_name", None)
        department_id = updates.pop("department_id", None)
        if department_id is not None:
            recurring.department_id = self._validate_department(db, principal, department_id)
        if vendor_name is not None:
            recurring.vendor_id = self._find_or_create_vendor(db, principal.organization_id, vendor_name, recurring.category)
        for key, value in updates.items():
            setattr(recurring, key, value)
        db.commit()
        db.refresh(recurring)
        return recurring

    def list_recurring_requests(self, db: Session, principal: AuthenticatedPrincipal) -> list[RecurringExpenseRequest]:
        query = (
            db.query(RecurringExpenseRequest)
            .options(joinedload(RecurringExpenseRequest.department))
            .filter(RecurringExpenseRequest.organization_id == principal.organization_id)
            .order_by(RecurringExpenseRequest.created_at.desc())
        )
        if principal.role == ROLE_DEPT_HEAD:
            query = query.filter(RecurringExpenseRequest.department_id == principal.department_id)
        elif principal.role == ROLE_EMPLOYEE:
            query = query.filter(RecurringExpenseRequest.requested_by_user_id == principal.user_id)
        return query.all()

    def create_recurring_request(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        payload: RecurringExpenseRequestCreateRequest,
    ) -> RecurringExpenseRequest:
        if principal.role not in {ROLE_DEPT_HEAD}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only department heads can request recurring expenses")
        if not principal.department_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department assignment is required")
        request = RecurringExpenseRequest(
            organization_id=principal.organization_id,
            department_id=principal.department_id,
            requested_by_user_id=principal.user_id,
            vendor_name=payload.vendor_name,
            name=payload.name,
            category=payload.category,
            estimated_amount=payload.estimated_amount,
            currency=payload.currency,
            billing_cycle=payload.billing_cycle,
            reason=payload.reason,
            bill_document_id=payload.bill_document_id,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="recurring_expense_request",
            resource_id=request.id,
            action="created",
            details={"name": request.name, "amount": str(request.estimated_amount)},
        )
        return request

    def decide_recurring_request(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        request_id: str,
        payload: RecurringExpenseRequestDecisionRequest,
    ) -> RecurringExpenseRequest:
        self._require_org_owner(principal)
        request = (
            db.query(RecurringExpenseRequest)
            .options(joinedload(RecurringExpenseRequest.department))
            .filter(
                RecurringExpenseRequest.id == request_id,
                RecurringExpenseRequest.organization_id == principal.organization_id,
            )
            .first()
        )
        if request is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring expense request not found")
        if payload.approved:
            request.status = "approved"
            request.approved_by_user_id = principal.user_id
            request.approved_at = datetime.now(UTC)
            recurring = RecurringExpense(
                organization_id=principal.organization_id,
                department_id=request.department_id,
                vendor_id=self._find_or_create_vendor(db, principal.organization_id, request.vendor_name, request.category),
                bill_document_id=request.bill_document_id,
                name=request.name,
                category=request.category,
                amount=request.estimated_amount,
                currency=request.currency,
                billing_cycle=request.billing_cycle,
                priority="pay_this_week",
                criticality="medium",
                created_by_user_id=principal.user_id,
                next_due_date=date.today() + timedelta(days=7),
            )
            db.add(recurring)
        else:
            request.status = "rejected"
            request.rejection_reason = payload.rejection_reason
            request.approved_by_user_id = principal.user_id
            request.approved_at = datetime.now(UTC)
        db.commit()
        db.refresh(request)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="recurring_expense_request",
            resource_id=request.id,
            action="approved" if payload.approved else "rejected",
            details={"name": request.name},
        )
        return request

    def list_spend_limits(self, db: Session, principal: AuthenticatedPrincipal) -> list[SpendLimit]:
        query = (
            db.query(SpendLimit)
            .options(joinedload(SpendLimit.department))
            .filter(SpendLimit.organization_id == principal.organization_id)
            .order_by(SpendLimit.created_at.desc())
        )
        if principal.role == ROLE_DEPT_HEAD:
            query = query.filter((SpendLimit.department_id == principal.department_id) | (SpendLimit.department_id.is_(None)))
        elif principal.role == ROLE_EMPLOYEE:
            query = query.filter((SpendLimit.user_id == principal.user_id) | (SpendLimit.department_id == principal.department_id))
        return query.all()

    def create_spend_limit(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        payload: SpendLimitCreateRequest,
    ) -> SpendLimit:
        self._require_org_owner(principal)
        department_id = self._validate_department(db, principal, payload.department_id) if payload.department_id else None
        spend_limit = SpendLimit(
            organization_id=principal.organization_id,
            department_id=department_id,
            user_id=payload.user_id,
            category=payload.category,
            max_single_expense_amount=payload.max_single_expense_amount,
            monthly_limit=payload.monthly_limit,
            requires_approval_above_amount=payload.requires_approval_above_amount,
            allowed_categories_json=payload.allowed_categories,
            recurring_creation_restricted=payload.recurring_creation_restricted,
            variable_requires_org_owner=payload.variable_requires_org_owner,
            active=payload.active,
            created_by_user_id=principal.user_id,
        )
        db.add(spend_limit)
        db.commit()
        db.refresh(spend_limit)
        return spend_limit

    def update_spend_limit(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        spend_limit_id: str,
        payload: SpendLimitUpdateRequest,
    ) -> SpendLimit:
        self._require_org_owner(principal)
        spend_limit = (
            db.query(SpendLimit)
            .options(joinedload(SpendLimit.department))
            .filter(
                SpendLimit.id == spend_limit_id,
                SpendLimit.organization_id == principal.organization_id,
            )
            .first()
        )
        if spend_limit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spend limit not found")
        updates = payload.model_dump(exclude_unset=True)
        if "department_id" in updates:
            department_id = updates.pop("department_id")
            spend_limit.department_id = self._validate_department(db, principal, department_id) if department_id else None
        if "allowed_categories" in updates:
            spend_limit.allowed_categories_json = updates.pop("allowed_categories")
        for key, value in updates.items():
            setattr(spend_limit, key, value)
        db.commit()
        db.refresh(spend_limit)
        return spend_limit

    def recalculate_payment_priorities(self, db: Session, principal: AuthenticatedPrincipal) -> list[PaymentPriority]:
        today = date.today()
        end_of_week = today + timedelta(days=7)
        items: list[PaymentPriority] = []

        recurring_items = self.list_recurring_expenses(db, principal if principal.role == ROLE_ORG_OWNER else self._as_org_owner_view(principal))
        for recurring in recurring_items:
            due_date = recurring.next_due_date
            if recurring.status != "active":
                continue
            priority = self._priority_for_due_date(due_date, today, end_of_week)
            reason = f"{recurring.name} is {priority.replace('_', ' ')} due to billing schedule and criticality {recurring.criticality}."
            items.append(
                PaymentPriority(
                    organization_id=principal.organization_id,
                    expense_type="recurring",
                    expense_id=recurring.id,
                    priority=priority,
                    reason=reason,
                    due_date=due_date,
                    estimated_cash_out_date=due_date,
                )
            )

        variable_items = self.list_variable_expenses(db, principal if principal.role == ROLE_ORG_OWNER else self._as_org_owner_view(principal))
        for expense in variable_items:
            if expense.status not in {"approved_by_org_owner", "paid"}:
                continue
            due_date = expense.expense_date
            priority = "blocked" if expense.payment_status == "paid" else self._priority_for_due_date(due_date, today, end_of_week)
            reason = (
                "Payment already completed."
                if priority == "blocked"
                else f"{expense.title} is approved and awaiting payment for {expense.department.name if expense.department else 'company operations'}."
            )
            items.append(
                PaymentPriority(
                    organization_id=principal.organization_id,
                    expense_type="variable",
                    expense_id=expense.id,
                    priority=priority,
                    reason=reason,
                    due_date=due_date,
                    estimated_cash_out_date=due_date,
                )
            )

        db.query(PaymentPriority).filter(PaymentPriority.organization_id == principal.organization_id).delete()
        for item in items:
            db.add(item)
        db.commit()
        return (
            db.query(PaymentPriority)
            .filter(PaymentPriority.organization_id == principal.organization_id)
            .order_by(PaymentPriority.due_date.asc().nullslast())
            .all()
        )

    def build_dashboard(self, db: Session, principal: AuthenticatedPrincipal) -> DashboardOut:
        priorities = self.recalculate_payment_priorities(db, principal)
        budgets = self.list_budgets(db, principal)
        expenses = self.list_variable_expenses(db, principal)
        recurring_items = self.list_recurring_expenses(db, principal)
        current_month = date.today().month
        current_year = date.today().year

        total_variable = sum(
            (expense.amount for expense in expenses if expense.expense_date.month == current_month and expense.expense_date.year == current_year),
            Decimal("0"),
        )
        total_recurring = sum(
            (
                recurring.amount
                for recurring in recurring_items
                if recurring.next_due_date and recurring.next_due_date.month == current_month and recurring.next_due_date.year == current_year
            ),
            Decimal("0"),
        )
        approved_count = sum(1 for expense in expenses if expense.status in {"approved_by_org_owner", "paid"})
        rejected_count = sum(1 for expense in expenses if "rejected" in expense.status)
        pending_count = sum(1 for expense in expenses if expense.status in {"pending_dept_head", "forwarded_to_org_owner"})

        total_budget = sum((budget.amount for budget in budgets if budget.scope == "company"), Decimal("0"))
        total_budget_used = sum((self._budget_consumed(budget) for budget in budgets if budget.scope == "company"), Decimal("0"))

        category_rows = (
            db.query(ExpenseCategory.name, func.coalesce(func.sum(Expense.amount), 0))
            .join(Expense, Expense.category_id == ExpenseCategory.id)
            .filter(Expense.organization_id == principal.organization_id, Expense.expense_type == "variable")
            .group_by(ExpenseCategory.name)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        department_rows = (
            db.query(Department.name, func.coalesce(func.sum(Expense.amount), 0))
            .join(Expense, Expense.department_id == Department.id)
            .filter(Expense.organization_id == principal.organization_id, Expense.expense_type == "variable")
            .group_by(Department.name)
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        this_week = date.today() + timedelta(days=7)
        cash_out_week = sum(
            (
                self._priority_amount(db, principal.organization_id, item.expense_type, item.expense_id)
                for item in priorities
                if item.due_date and item.due_date <= this_week and item.priority in {"pay_now", "pay_this_week"}
            ),
            Decimal("0"),
        )
        cash_out_month = sum(
            (
                self._priority_amount(db, principal.organization_id, item.expense_type, item.expense_id)
                for item in priorities
                if item.due_date and item.due_date.month == current_month and item.due_date.year == current_year
            ),
            Decimal("0"),
        )
        budget_outs = [
            BudgetOut(
                id=budget.id,
                name=budget.name,
                scope=budget.scope,
                currency=budget.currency,
                amount=budget.amount,
                month=budget.month,
                year=budget.year,
                start_date=budget.start_date,
                end_date=budget.end_date,
                alert_threshold_percent=budget.alert_threshold_percent,
                status=budget.status,
                spent_amount=self._budget_consumed(budget),
                remaining_amount=max(budget.amount - self._budget_consumed(budget), Decimal("0")),
                department=budget.department,
                category=budget.category,
                created_at=budget.created_at,
                updated_at=budget.updated_at,
            )
            for budget in budgets
        ]
        priority_outs = [
            PaymentPriorityOut(
                id=item.id,
                expense_type=item.expense_type,
                expense_id=item.expense_id,
                label=item.expense_type.replace("_", " ").title(),
                amount=self._priority_amount(db, principal.organization_id, item.expense_type, item.expense_id),
                priority=item.priority,
                reason=item.reason,
                due_date=item.due_date,
                estimated_cash_out_date=item.estimated_cash_out_date,
            )
            for item in priorities
        ]
        return DashboardOut(
            organization_name=principal.organization_name,
            role=principal.role,
            total_spend_this_month=total_variable + total_recurring,
            recurring_spend_this_month=total_recurring,
            variable_spend_this_month=total_variable,
            pending_approvals=pending_count,
            approved_expenses=approved_count,
            rejected_expenses=rejected_count,
            company_budget_used=total_budget_used,
            company_budget_remaining=max(total_budget - total_budget_used, Decimal("0")),
            upcoming_payment_count=len(priorities),
            cash_outflow_this_week=cash_out_week,
            cash_outflow_this_month=cash_out_month,
            budgets=budget_outs,
            category_breakdown=[CategorySpendOut(category=name, amount=Decimal(str(amount))) for name, amount in category_rows],
            department_breakdown=[DepartmentSpendOut(department=name, amount=Decimal(str(amount))) for name, amount in department_rows],
            payment_priorities=priority_outs,
        )

    def list_audit_events(self, db: Session, principal: AuthenticatedPrincipal) -> list[AuditEvent]:
        self._require_org_owner(principal)
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.organization_id == principal.organization_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
            .all()
        )

    def _priority_amount(self, db: Session, organization_id: str, expense_type: str, expense_id: str) -> Decimal:
        if expense_type == "recurring":
            recurring = (
                db.query(RecurringExpense)
                .filter(RecurringExpense.id == expense_id, RecurringExpense.organization_id == organization_id)
                .first()
            )
            return recurring.amount if recurring else Decimal("0")
        expense = db.query(Expense).filter(Expense.id == expense_id, Expense.organization_id == organization_id).first()
        return expense.amount if expense else Decimal("0")

    def _priority_for_due_date(self, due_date: date | None, today: date, end_of_week: date) -> str:
        if due_date is None:
            return "needs_review"
        if due_date < today:
            return "pay_now"
        if due_date <= today + timedelta(days=2):
            return "pay_now"
        if due_date <= end_of_week:
            return "pay_this_week"
        if due_date <= today + timedelta(days=21):
            return "can_wait"
        return "needs_review"

    def _budget_consumed(self, budget: Budget) -> Decimal:
        return sum(
            (
                expense.amount
                for expense in budget.expenses
                if expense.status in {"approved_by_org_owner", "paid"}
                and budget.start_date <= expense.expense_date <= budget.end_date
            ),
            Decimal("0"),
        )

    def _validate_category(self, db: Session, principal: AuthenticatedPrincipal, category_id: str) -> str:
        category = self._get_category(db, principal.organization_id, category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense category not found")
        return category.id

    def _get_category(self, db: Session, organization_id: str, category_id: str | None) -> ExpenseCategory | None:
        if not category_id:
            return None
        return (
            db.query(ExpenseCategory)
            .filter(
                ExpenseCategory.id == category_id,
                ExpenseCategory.organization_id == organization_id,
            )
            .first()
        )

    def _validate_department(self, db: Session, principal: AuthenticatedPrincipal, department_id: str) -> str:
        department = (
            db.query(Department)
            .filter(Department.id == department_id, Department.organization_id == principal.organization_id)
            .first()
        )
        if department is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return department.id

    def _get_document(self, db: Session, organization_id: str, document_id: str) -> Document:
        document = (
            db.query(Document)
            .filter(Document.id == document_id, Document.organization_id == organization_id)
            .first()
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return document

    def _assert_expense_access(self, principal: AuthenticatedPrincipal, expense: Expense) -> None:
        if principal.role == ROLE_ORG_OWNER:
            return
        if principal.role == ROLE_DEPT_HEAD and expense.department_id == principal.department_id:
            return
        if principal.role == ROLE_EMPLOYEE and expense.submitted_by_user_id == principal.user_id:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    def _require_org_owner(self, principal: AuthenticatedPrincipal) -> None:
        if principal.role != ROLE_ORG_OWNER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization owner access required")

    def _find_or_create_vendor(self, db: Session, organization_id: str, vendor_name: str | None, category: str | None) -> str | None:
        if not vendor_name:
            return None
        vendor = (
            db.query(Vendor)
            .filter(Vendor.organization_id == organization_id, func.lower(Vendor.name) == vendor_name.lower())
            .first()
        )
        if vendor is None:
            vendor = Vendor(
                organization_id=organization_id,
                name=vendor_name,
                category=category,
                criticality="medium",
            )
            db.add(vendor)
            db.flush()
        return vendor.id

    def _evaluate_spend_limits(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        amount: Decimal,
        category: str | None,
    ) -> SpendLimit | None:
        limits = (
            db.query(SpendLimit)
            .filter(
                SpendLimit.organization_id == principal.organization_id,
                SpendLimit.active.is_(True),
            )
            .all()
        )
        applicable: list[SpendLimit] = []
        for item in limits:
            if item.user_id and item.user_id != principal.user_id:
                continue
            if item.department_id and item.department_id != principal.department_id:
                continue
            if item.category and item.category != category:
                continue
            applicable.append(item)
        for item in applicable:
            if item.allowed_categories_json and category and category not in item.allowed_categories_json:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is not allowed by spend limits")
            if item.max_single_expense_amount is not None and amount > item.max_single_expense_amount:
                return item
        return applicable[0] if applicable else None

    def _as_org_owner_view(self, principal: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            user_id=principal.user_id,
            email=principal.email,
            display_name=principal.display_name,
            role=ROLE_ORG_OWNER,
            platform_role=principal.platform_role,
            membership_id=principal.membership_id,
            organization_id=principal.organization_id,
            organization_name=principal.organization_name,
            organization_slug=principal.organization_slug,
            default_currency=principal.default_currency,
            membership_status=principal.membership_status,
            department_id=principal.department_id,
            department_name=principal.department_name,
            onboarding_completed=principal.onboarding_completed,
            tenant_id=principal.tenant_id,
            entra_oid=principal.entra_oid,
            session_id=principal.session_id,
        )
