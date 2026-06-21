from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.security import AuthenticatedPrincipal
from app.models import AIChatMessage, AIChatSession, Expense, RecurringExpense
from app.services.ai_agent_service import AIAgentService
from app.services.finance_service import FinanceService

logger = logging.getLogger(__name__)


class AIChatService:
    def __init__(self) -> None:
        self.finance_service = FinanceService()
        self.agent_service = AIAgentService()

    def list_sessions(self, db: Session, principal: AuthenticatedPrincipal) -> list[AIChatSession]:
        return (
            db.query(AIChatSession)
            .options(joinedload(AIChatSession.messages))
            .filter(
                AIChatSession.organization_id == principal.organization_id,
                AIChatSession.user_id == principal.user_id,
            )
            .order_by(AIChatSession.updated_at.desc())
            .all()
        )

    def ask(self, db: Session, principal: AuthenticatedPrincipal, message: str, session_id: str | None) -> tuple[AIChatSession, AIChatMessage]:
        session = self._get_or_create_session(db, principal, session_id, message)
        user_message = AIChatMessage(
            organization_id=principal.organization_id,
            session_id=session.id,
            role="user",
            content=message,
        )
        db.add(user_message)
        db.flush()
        history = self._build_history(session, message)
        try:
            agent_answer = self.agent_service.answer(db, principal, message, history)
            reply_text = agent_answer.answer or self._build_grounded_reply(db, principal, message)[0]
            grounded_context = {
                **agent_answer.grounded_context,
                "sources": agent_answer.sources,
                "suggested_followups": agent_answer.suggested_followups,
                "fallback_used": False,
            }
        except Exception as exc:
            logger.warning("AI agent reply failed, using deterministic fallback: %s", exc)
            reply_text, grounded_context = self._build_grounded_reply(db, principal, message)
            grounded_context = {
                **grounded_context,
                "sources": [{"label": "Finance dashboard", "type": "tool", "tool_name": "get_finance_dashboard_summary"}],
                "suggested_followups": [],
                "used_tools": ["get_finance_dashboard_summary"],
                "confidence": "medium",
                "fallback_used": True,
            }
        reply = AIChatMessage(
            organization_id=principal.organization_id,
            session_id=session.id,
            role="assistant",
            content=reply_text,
            grounded_context_json=grounded_context,
        )
        db.add(reply)
        db.commit()
        db.refresh(session)
        db.refresh(reply)
        return session, reply

    def _build_history(self, session: AIChatSession, pending_message: str) -> list[dict[str, str]]:
        history = [{"role": item.role, "content": item.content} for item in session.messages]
        history.append({"role": "user", "content": pending_message})
        return history

    def _get_or_create_session(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        session_id: str | None,
        message: str,
    ) -> AIChatSession:
        if session_id:
            session = (
                db.query(AIChatSession)
                .options(joinedload(AIChatSession.messages))
                .filter(
                    AIChatSession.id == session_id,
                    AIChatSession.organization_id == principal.organization_id,
                    AIChatSession.user_id == principal.user_id,
                )
                .first()
            )
            if session is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI chat session not found")
            return session
        session = AIChatSession(
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            title=message[:80],
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    def _build_grounded_reply(self, db: Session, principal: AuthenticatedPrincipal, message: str) -> tuple[str, dict]:
        dashboard = self.finance_service.build_dashboard(db, principal)
        priorities = self.finance_service.recalculate_payment_priorities(db, principal)
        top_priority = priorities[0] if priorities else None
        pending = dashboard.pending_approvals
        overspending = dashboard.company_budget_remaining < 0
        highest_department = dashboard.department_breakdown[0] if dashboard.department_breakdown else None
        recurring_due = (
            db.query(RecurringExpense)
            .filter(RecurringExpense.organization_id == principal.organization_id, RecurringExpense.status == "active")
            .order_by(RecurringExpense.next_due_date.asc().nullslast())
            .limit(5)
            .all()
        )
        approved_unpaid = (
            db.query(Expense)
            .filter(
                Expense.organization_id == principal.organization_id,
                Expense.expense_type == "variable",
                Expense.status.in_(["approved_by_dept_head", "approved_by_org_owner"]),
                Expense.payment_status != "paid",
            )
            .count()
        )
        lowered = message.lower()
        parts: list[str] = []

        if "cash flow" in lowered or "outflow" in lowered:
            parts.append(
                f"Cash outflow this week is {dashboard.cash_outflow_this_week} {principal.default_currency}, and this month is {dashboard.cash_outflow_this_month} {principal.default_currency}."
            )
        if "overspend" in lowered or "budget" in lowered:
            parts.append(
                f"Company budget used is {dashboard.company_budget_used} with {dashboard.company_budget_remaining} remaining."
            )
        if "department" in lowered and highest_department:
            parts.append(f"{highest_department.department} is currently the highest-spend department at {highest_department.amount} {principal.default_currency}.")
        if "urgent" in lowered or "pay" in lowered:
            if top_priority:
                parts.append(f"The most urgent payment is a {top_priority.expense_type} item tagged `{top_priority.priority}` because {top_priority.reason}")
            else:
                parts.append("No urgent payment records were found in the current tenant data.")
        if "pending" in lowered or "approve" in lowered:
            parts.append(f"There are {pending} approval items pending, and {approved_unpaid} approved variable expenses still waiting for payment.")
        if "recurring" in lowered:
            if recurring_due:
                parts.append("Upcoming recurring payments: " + ", ".join(item.name for item in recurring_due[:3]) + ".")
            else:
                parts.append("No active recurring payments with due dates were found.")

        if not parts:
            parts.append(
                f"This month shows {dashboard.total_spend_this_month} {principal.default_currency} in tracked spend, with {pending} pending approvals."
            )
            if highest_department:
                parts.append(f"The highest visible department spend is {highest_department.department} at {highest_department.amount} {principal.default_currency}.")
            if top_priority:
                parts.append(f"Top payment priority: {top_priority.priority} for {top_priority.expense_type} because {top_priority.reason}")
            if dashboard.company_budget_remaining < Decimal('0'):
                parts.append("Budget data indicates the company is over plan and should review non-critical payments first.")
            elif dashboard.company_budget_remaining == Decimal('0'):
                parts.append("Budget remaining is fully consumed, so any new approvals should be reviewed carefully.")
            else:
                parts.append("Budget headroom still exists, but urgent and overdue items should be reviewed first.")

        grounded_context = {
            "organization_name": principal.organization_name,
            "total_spend_this_month": str(dashboard.total_spend_this_month),
            "pending_approvals": pending,
            "company_budget_remaining": str(dashboard.company_budget_remaining),
            "top_department": highest_department.department if highest_department else None,
            "top_priority": top_priority.priority if top_priority else None,
            "top_priority_reason": top_priority.reason if top_priority else None,
            "overspending": overspending,
        }
        return " ".join(parts), grounded_context
