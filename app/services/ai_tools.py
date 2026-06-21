from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.rbac import ROLE_DEPT_HEAD, ROLE_EMPLOYEE, ROLE_ORG_OWNER
from app.core.security import AuthenticatedPrincipal
from app.models import Department, Document, Expense, ExpenseCategory
from app.services.ai_knowledge_base import explain_concept
from app.services.document_service import DocumentService
from app.services.finance_service import FinanceService
from app.services.storage_service import StorageService


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    source_label: str
    payload: dict[str, Any]


class AIToolbox:
    MAX_ROWS = 5
    MAX_TEXT_EXCERPT_CHARS = 2400
    DEFAULT_LOOKBACK_DAYS = 30

    def __init__(self) -> None:
        self.finance_service = FinanceService()
        self.document_service = DocumentService()
        self.storage_service = StorageService()

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            self._tool(
                "get_finance_dashboard_summary",
                "Return a compact tenant-scoped dashboard summary for the current user.",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
            self._tool(
                "get_budget_summary",
                "Return compact company and department budget summaries visible to the current user.",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
            self._tool(
                "get_department_spend_breakdown",
                "Return top departments by spend. Use small limits only.",
                {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "get_pending_approvals_summary",
                "Return pending approval counts and a small list of visible approval items.",
                {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "get_urgent_payments",
                "Return the most urgent visible payments with reasons and due dates.",
                {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 5}},
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "get_recurring_expenses_summary",
                "Return upcoming recurring expenses with small bounded limits.",
                {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "search_expenses_summary",
                "Search variable expenses with bounded filters such as status, vendor, date range, department, or amount range.",
                {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "vendor": {"type": "string"},
                        "department": {"type": "string"},
                        "category": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "amount_min": {"type": "number"},
                        "amount_max": {"type": "number"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "get_expense_detail",
                "Return one visible expense by id.",
                {
                    "type": "object",
                    "properties": {"expense_id": {"type": "string"}},
                    "required": ["expense_id"],
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "list_relevant_documents",
                "Return visible document metadata filtered by expense, vendor, type, or date range.",
                {
                    "type": "object",
                    "properties": {
                        "expense_id": {"type": "string"},
                        "vendor": {"type": "string"},
                        "status": {"type": "string"},
                        "content_type": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                    },
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "get_document_scan_summary",
                "Return the latest stored scan summary for a visible document.",
                {
                    "type": "object",
                    "properties": {"document_id": {"type": "string"}},
                    "required": ["document_id"],
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "get_document_text_excerpt",
                "Return a short safe excerpt for a visible document when scan metadata is insufficient.",
                {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "max_chars": {"type": "integer", "minimum": 250, "maximum": 2400},
                    },
                    "required": ["document_id"],
                    "additionalProperties": False,
                },
            ),
            self._tool(
                "explain_app_concept",
                "Answer product and workflow questions using only the curated SpendPilot knowledge base.",
                {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                    "additionalProperties": False,
                },
            ),
        ]

    def execute(self, db: Session, principal: AuthenticatedPrincipal, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        handlers = {
            "get_finance_dashboard_summary": self.get_finance_dashboard_summary,
            "get_budget_summary": self.get_budget_summary,
            "get_department_spend_breakdown": self.get_department_spend_breakdown,
            "get_pending_approvals_summary": self.get_pending_approvals_summary,
            "get_urgent_payments": self.get_urgent_payments,
            "get_recurring_expenses_summary": self.get_recurring_expenses_summary,
            "search_expenses_summary": self.search_expenses_summary,
            "get_expense_detail": self.get_expense_detail,
            "list_relevant_documents": self.list_relevant_documents,
            "get_document_scan_summary": self.get_document_scan_summary,
            "get_document_text_excerpt": self.get_document_text_excerpt,
            "explain_app_concept": self.explain_app_concept,
        }
        if tool_name not in handlers:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported AI tool: {tool_name}")
        return handlers[tool_name](db, principal, **arguments)

    def get_finance_dashboard_summary(self, db: Session, principal: AuthenticatedPrincipal) -> ToolExecutionResult:
        dashboard = self.finance_service.build_dashboard(db, principal)
        priorities = self.finance_service.recalculate_payment_priorities(db, principal)
        top_priority = priorities[0] if priorities else None
        top_department = dashboard.department_breakdown[0] if dashboard.department_breakdown else None
        payload = {
            "organization_name": principal.organization_name,
            "role": principal.role,
            "currency": principal.default_currency,
            "time_range": {"label": "current_month"},
            "monthly_spend": str(dashboard.total_spend_this_month),
            "weekly_cash_outflow": str(dashboard.cash_outflow_this_week),
            "monthly_cash_outflow": str(dashboard.cash_outflow_this_month),
            "pending_approvals": dashboard.pending_approvals,
            "company_budget_used": str(dashboard.company_budget_used),
            "company_budget_remaining": str(dashboard.company_budget_remaining),
            "top_department": (
                {"department": top_department.department, "amount": str(top_department.amount)} if top_department else None
            ),
            "top_payment_priority": (
                {
                    "label": top_priority.label,
                    "priority": top_priority.priority,
                    "reason": top_priority.reason,
                    "amount": str(top_priority.amount),
                    "due_date": top_priority.due_date.isoformat() if top_priority.due_date else None,
                }
                if top_priority
                else None
            ),
        }
        return ToolExecutionResult("get_finance_dashboard_summary", "Finance dashboard", payload)

    def get_budget_summary(self, db: Session, principal: AuthenticatedPrincipal) -> ToolExecutionResult:
        dashboard = self.finance_service.build_dashboard(db, principal)
        visible_budgets = dashboard.budgets[: self.MAX_ROWS]
        payload = {
            "currency": principal.default_currency,
            "company_budget_used": str(dashboard.company_budget_used),
            "company_budget_remaining": str(dashboard.company_budget_remaining),
            "visible_budgets": [
                {
                    "id": budget.id,
                    "name": budget.name,
                    "scope": budget.scope,
                    "amount": str(budget.amount),
                    "spent_amount": str(budget.spent_amount),
                    "remaining_amount": str(budget.remaining_amount),
                    "month": budget.month,
                    "year": budget.year,
                    "department": budget.department.name if budget.department else None,
                }
                for budget in visible_budgets
            ],
        }
        return ToolExecutionResult("get_budget_summary", "Budget summary", payload)

    def get_department_spend_breakdown(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        limit: int = 5,
    ) -> ToolExecutionResult:
        dashboard = self.finance_service.build_dashboard(db, principal)
        payload = {
            "currency": principal.default_currency,
            "departments": [
                {"department": item.department, "amount": str(item.amount)}
                for item in dashboard.department_breakdown[: self._clamp_limit(limit)]
            ],
        }
        return ToolExecutionResult("get_department_spend_breakdown", "Department spend", payload)

    def get_pending_approvals_summary(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        limit: int = 5,
    ) -> ToolExecutionResult:
        query = self._visible_variable_expenses_query(db, principal).filter(
            Expense.status.in_(["pending_dept_head", "forwarded_to_org_owner"])
        )
        items = query.order_by(Expense.created_at.desc()).limit(self._clamp_limit(limit)).all()
        payload = {
            "pending_count": query.count(),
            "items": [self._expense_summary(item) for item in items],
        }
        return ToolExecutionResult("get_pending_approvals_summary", "Pending approvals", payload)

    def get_urgent_payments(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        limit: int = 5,
    ) -> ToolExecutionResult:
        priorities = self.finance_service.recalculate_payment_priorities(db, principal)
        payload = {
            "items": [
                {
                    "expense_id": item.expense_id,
                    "expense_type": item.expense_type,
                    "label": item.label,
                    "priority": item.priority,
                    "reason": item.reason,
                    "amount": str(item.amount),
                    "due_date": item.due_date.isoformat() if item.due_date else None,
                }
                for item in priorities[: self._clamp_limit(limit)]
            ]
        }
        return ToolExecutionResult("get_urgent_payments", "Urgent payments", payload)

    def get_recurring_expenses_summary(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        limit: int = 5,
    ) -> ToolExecutionResult:
        items = self.finance_service.list_recurring_expenses(db, principal)[: self._clamp_limit(limit, upper=10)]
        payload = {
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "vendor": item.vendor.name if item.vendor else None,
                    "amount": str(item.amount),
                    "currency": item.currency,
                    "category": item.category,
                    "due_date": item.next_due_date.isoformat() if item.next_due_date else None,
                    "status": item.status,
                    "priority": item.priority,
                }
                for item in items
            ]
        }
        return ToolExecutionResult("get_recurring_expenses_summary", "Recurring expenses", payload)

    def search_expenses_summary(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        *,
        status: str | None = None,
        vendor: str | None = None,
        department: str | None = None,
        category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        amount_min: float | None = None,
        amount_max: float | None = None,
        limit: int = 5,
    ) -> ToolExecutionResult:
        query = self._visible_variable_expenses_query(db, principal)
        normalized_date_from, normalized_date_to, used_default_range = self._resolve_date_range(date_from, date_to)
        query = query.filter(Expense.expense_date >= normalized_date_from, Expense.expense_date <= normalized_date_to)
        if status:
            query = query.filter(Expense.status == status)
        if vendor:
            query = query.filter(func.lower(Expense.vendor_name).contains(vendor.lower()))
        if department:
            query = query.filter(Expense.department.has(func.lower(Department.name).contains(department.lower())))
        if category:
            query = query.filter(Expense.category.has(func.lower(ExpenseCategory.name).contains(category.lower())))
        if amount_min is not None:
            query = query.filter(Expense.amount >= Decimal(str(amount_min)))
        if amount_max is not None:
            query = query.filter(Expense.amount <= Decimal(str(amount_max)))

        items = query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(self._clamp_limit(limit)).all()
        payload = {
            "time_range": {
                "date_from": normalized_date_from.isoformat(),
                "date_to": normalized_date_to.isoformat(),
                "used_default_range": used_default_range,
            },
            "result_count": len(items),
            "items": [self._expense_summary(item) for item in items],
        }
        return ToolExecutionResult("search_expenses_summary", "Expense search", payload)

    def get_expense_detail(self, db: Session, principal: AuthenticatedPrincipal, expense_id: str) -> ToolExecutionResult:
        expense = self.finance_service.get_variable_expense(db, principal, expense_id)
        payload = {
            "expense": {
                **self._expense_summary(expense),
                "description": expense.description,
                "policy_status": expense.policy_status,
                "payment_status": expense.payment_status,
                "rejection_reason": expense.rejection_reason,
                "documents": [{"id": doc.id, "filename": doc.filename, "status": doc.status} for doc in expense.documents[: self.MAX_ROWS]],
                "approvals": [
                    {
                        "action": item.action,
                        "comment": item.comment,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in expense.approvals[: self.MAX_ROWS]
                ],
            }
        }
        return ToolExecutionResult("get_expense_detail", "Expense detail", payload)

    def list_relevant_documents(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        *,
        expense_id: str | None = None,
        vendor: str | None = None,
        status: str | None = None,
        content_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 5,
    ) -> ToolExecutionResult:
        query = self._visible_documents_query(db, principal)
        if expense_id:
            query = query.filter(Document.expense_id == expense_id)
        if vendor:
            query = query.join(Document.expense, isouter=True).filter(func.lower(Expense.vendor_name).contains(vendor.lower()))
        if status:
            query = query.filter(Document.status == status)
        if content_type:
            query = query.filter(Document.content_type == content_type)
        normalized_date_from, normalized_date_to, used_default_range = self._resolve_date_range(date_from, date_to)
        query = query.filter(
            func.date(Document.created_at) >= normalized_date_from.isoformat(),
            func.date(Document.created_at) <= normalized_date_to.isoformat(),
        )
        items = query.order_by(Document.created_at.desc()).limit(self._clamp_limit(limit)).all()
        payload = {
            "time_range": {
                "date_from": normalized_date_from.isoformat(),
                "date_to": normalized_date_to.isoformat(),
                "used_default_range": used_default_range,
            },
            "documents": [
                {
                    "id": item.id,
                    "filename": item.filename,
                    "status": item.status,
                    "content_type": item.content_type,
                    "expense_id": item.expense_id,
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ],
        }
        return ToolExecutionResult("list_relevant_documents", "Documents", payload)

    def get_document_scan_summary(self, db: Session, principal: AuthenticatedPrincipal, document_id: str) -> ToolExecutionResult:
        scan = self.document_service.get_latest_scan(db, principal, document_id)
        payload = {
            "document_id": document_id,
            "summary": scan.summary,
            "risk_level": scan.risk_level,
            "provider_status": scan.provider_status,
            "findings": scan.findings[: self.MAX_ROWS],
            "recommendations": scan.recommendations[: self.MAX_ROWS],
            "extracted_expense": scan.extracted_expense.model_dump(mode="json") if scan.extracted_expense else None,
        }
        return ToolExecutionResult("get_document_scan_summary", "Document scan", payload)

    def get_document_text_excerpt(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        document_id: str,
        max_chars: int = 1200,
    ) -> ToolExecutionResult:
        document = self.document_service.get_document(db, principal, document_id)
        excerpt_limit = min(max_chars, self.MAX_TEXT_EXCERPT_CHARS)
        text = (document.extracted_text or "").strip()
        source = "stored_extracted_text"
        if not text:
            if document.content_type.startswith("text/") or document.filename.lower().endswith((".txt", ".md", ".json", ".csv")):
                blob = self.storage_service.read_bytes(document.storage_kind, document.storage_path)
                text = blob.decode("utf-8", errors="ignore").strip()
                source = "blob_excerpt"
            else:
                text = "No safe plain-text excerpt is available for this binary document. Use the stored scan summary instead."
                source = "no_safe_excerpt"
        payload = {
            "document_id": document_id,
            "source": source,
            "excerpt": text[:excerpt_limit],
            "truncated": len(text) > excerpt_limit,
        }
        return ToolExecutionResult("get_document_text_excerpt", "Document excerpt", payload)

    def explain_app_concept(self, db: Session, principal: AuthenticatedPrincipal, question: str) -> ToolExecutionResult:
        del db, principal
        return ToolExecutionResult("explain_app_concept", "Knowledge base", explain_concept(question))

    @staticmethod
    def result_to_message(result: ToolExecutionResult) -> str:
        return json.dumps(
            {
                "source_label": result.source_label,
                "tool_name": result.tool_name,
                "result": result.payload,
            },
            default=str,
            separators=(",", ":"),
        )

    @staticmethod
    def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }

    def _visible_variable_expenses_query(self, db: Session, principal: AuthenticatedPrincipal):
        query = (
            db.query(Expense)
            .options(joinedload(Expense.department), joinedload(Expense.category), joinedload(Expense.documents), joinedload(Expense.approvals))
            .filter(Expense.organization_id == principal.organization_id, Expense.expense_type == "variable")
        )
        if principal.role == ROLE_DEPT_HEAD:
            query = query.filter(Expense.department_id == principal.department_id)
        elif principal.role == ROLE_EMPLOYEE:
            query = query.filter(Expense.submitted_by_user_id == principal.user_id)
        return query

    def _visible_documents_query(self, db: Session, principal: AuthenticatedPrincipal):
        query = (
            db.query(Document)
            .options(joinedload(Document.scans), joinedload(Document.expense))
            .filter(Document.organization_id == principal.organization_id)
        )
        if principal.role == ROLE_ORG_OWNER:
            return query
        if principal.role == ROLE_DEPT_HEAD:
            return query.filter(Document.department_id == principal.department_id)
        return query.filter(Document.owner_user_id == principal.user_id)

    def _expense_summary(self, expense: Expense) -> dict[str, Any]:
        return {
            "id": expense.id,
            "title": expense.title,
            "vendor_name": expense.vendor_name,
            "amount": str(expense.amount),
            "currency": expense.currency,
            "expense_date": expense.expense_date.isoformat(),
            "status": expense.status,
            "department": expense.department.name if expense.department else None,
            "category": expense.category.name if expense.category else None,
        }

    def _resolve_date_range(self, date_from: str | None, date_to: str | None) -> tuple[date, date, bool]:
        today = datetime.now(UTC).date()
        used_default = False
        if date_to:
            resolved_to = date.fromisoformat(date_to)
        else:
            resolved_to = today
            used_default = True
        if date_from:
            resolved_from = date.fromisoformat(date_from)
        else:
            resolved_from = resolved_to - timedelta(days=self.DEFAULT_LOOKBACK_DAYS)
            used_default = True
        if resolved_from > resolved_to:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date_from must be on or before date_to")
        return resolved_from, resolved_to, used_default

    def _clamp_limit(self, limit: int, *, upper: int | None = None) -> int:
        max_limit = upper or self.MAX_ROWS
        return max(1, min(limit, max_limit))
