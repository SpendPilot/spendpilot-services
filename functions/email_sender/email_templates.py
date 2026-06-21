from __future__ import annotations

from dataclasses import dataclass

try:
    from .models import EmailRequest, EmailTemplateType
except ImportError:  # pragma: no cover - Azure Functions loads from the project root.
    from models import EmailRequest, EmailTemplateType


@dataclass
class RenderedEmail:
    subject: str
    plain_text: str
    html: str


def render_email(request: EmailRequest) -> RenderedEmail:
    template = request.type
    data = request.data
    display_name = data.get("displayName") or "there"
    organization_name = data.get("organizationName") or "SpendPilot"
    expense_title = data.get("title") or "Expense"
    amount = data.get("amount") or "0.00"
    currency = data.get("currency") or ""
    status = data.get("status") or ""
    rejection_reason = data.get("rejectionReason") or "No reason was supplied."
    submitted_by = data.get("submittedByEmail") or "a teammate"
    department_name = data.get("departmentName") or "your team"
    reset_url = data.get("resetUrl") or "https://costpilot.online/login"

    if template == EmailTemplateType.WELCOME_EMAIL:
        return RenderedEmail(
            subject=f"Welcome to {organization_name}",
            plain_text=(
                f"Hi {display_name},\n\n"
                f"Welcome to {organization_name} on SpendPilot. Your account is ready, and your current role is "
                f"{data.get('role', 'employee')}.\n"
            ),
            html=(
                f"<p>Hi {display_name},</p>"
                f"<p>Welcome to <strong>{organization_name}</strong> on SpendPilot. "
                f"Your account is ready, and your current role is <strong>{data.get('role', 'employee')}</strong>.</p>"
            ),
        )

    if template == EmailTemplateType.PASSWORD_RESET:
        return RenderedEmail(
            subject="Reset your SpendPilot password",
            plain_text=(
                f"Hi {display_name},\n\n"
                f"Use this link to reset your password: {reset_url}\n"
            ),
            html=(
                f"<p>Hi {display_name},</p>"
                f"<p>Use this link to reset your password: <a href=\"{reset_url}\">{reset_url}</a></p>"
            ),
        )

    if template == EmailTemplateType.EXPENSE_SUBMITTED:
        return RenderedEmail(
            subject=f"Expense submitted: {expense_title}",
            plain_text=(
                f"{submitted_by} submitted {expense_title} for {currency} {amount} in {department_name}. "
                f"Current status: {status}."
            ),
            html=(
                f"<p><strong>{submitted_by}</strong> submitted <strong>{expense_title}</strong> "
                f"for <strong>{currency} {amount}</strong> in <strong>{department_name}</strong>.</p>"
                f"<p>Current status: <strong>{status}</strong>.</p>"
            ),
        )

    if template == EmailTemplateType.EXPENSE_APPROVED:
        return RenderedEmail(
            subject=f"Expense approved: {expense_title}",
            plain_text=(
                f"Your expense {expense_title} for {currency} {amount} was approved. "
                f"Current status: {status}."
            ),
            html=(
                f"<p>Your expense <strong>{expense_title}</strong> for <strong>{currency} {amount}</strong> "
                f"was approved.</p><p>Current status: <strong>{status}</strong>.</p>"
            ),
        )

    return RenderedEmail(
        subject=f"Expense rejected: {expense_title}",
        plain_text=(
            f"Your expense {expense_title} for {currency} {amount} was rejected. "
            f"Reason: {rejection_reason}"
        ),
        html=(
            f"<p>Your expense <strong>{expense_title}</strong> for <strong>{currency} {amount}</strong> was rejected.</p>"
            f"<p>Reason: {rejection_reason}</p>"
        ),
    )
