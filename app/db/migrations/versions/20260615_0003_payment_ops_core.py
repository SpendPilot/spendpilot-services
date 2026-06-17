"""Add payment operations core models

Revision ID: 20260615_0003
Revises: 20260615_0002
Create Date: 2026-06-15 00:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260615_0003"
down_revision = "20260615_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("criticality", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("contact_info", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_vendor_name"),
    )
    op.create_index("ix_vendors_organization_id", "vendors", ["organization_id"], unique=False)

    op.create_table(
        "recurring_expenses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(length=36), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("bill_document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("billing_cycle", sa.String(length=30), nullable=False, server_default="monthly"),
        sa.Column("due_day", sa.Integer(), nullable=True),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="pay_this_week"),
        sa.Column("criticality", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recurring_expenses_organization_id", "recurring_expenses", ["organization_id"], unique=False)

    op.create_table(
        "recurring_expense_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(length=36), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vendor_name", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("estimated_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("billing_cycle", sa.String(length=30), nullable=False, server_default="monthly"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("bill_document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recurring_expense_requests_organization_id", "recurring_expense_requests", ["organization_id"], unique=False)

    op.create_table(
        "spend_limits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(length=36), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("max_single_expense_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("requires_approval_above_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("allowed_categories_json", sa.JSON(), nullable=True),
        sa.Column("recurring_creation_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("variable_requires_org_owner", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spend_limits_organization_id", "spend_limits", ["organization_id"], unique=False)

    op.create_table(
        "payment_priorities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_type", sa.String(length=20), nullable=False),
        sa.Column("expense_id", sa.String(length=36), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("estimated_cash_out_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payment_priorities_organization_id", "payment_priorities", ["organization_id"], unique=False)
    op.create_index("ix_payment_priorities_expense_id", "payment_priorities", ["expense_id"], unique=False)

    op.create_table(
        "ai_chat_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_chat_sessions_organization_id", "ai_chat_sessions", ["organization_id"], unique=False)

    op.create_table(
        "ai_chat_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("grounded_context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_chat_messages_organization_id", "ai_chat_messages", ["organization_id"], unique=False)

    with op.batch_alter_table("budgets", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("department_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("scope", sa.String(length=20), nullable=False, server_default="company"))
        batch_op.add_column(sa.Column("month", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("year", sa.Integer(), nullable=True))
        batch_op.create_index("ix_budgets_department_id", ["department_id"], unique=False)
        batch_op.create_foreign_key("fk_budgets_department_id_departments", "departments", ["department_id"], ["id"])

    with op.batch_alter_table("expenses", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("department_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("vendor_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("expense_type", sa.String(length=20), nullable=False, server_default="variable"))
        batch_op.add_column(sa.Column("dept_head_reviewer_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("org_owner_approver_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("payment_status", sa.String(length=20), nullable=False, server_default="unpaid"))
        batch_op.create_index("ix_expenses_department_id", ["department_id"], unique=False)
        batch_op.create_index("ix_expenses_vendor_id", ["vendor_id"], unique=False)
        batch_op.create_index("ix_expenses_dept_head_reviewer_user_id", ["dept_head_reviewer_user_id"], unique=False)
        batch_op.create_index("ix_expenses_org_owner_approver_user_id", ["org_owner_approver_user_id"], unique=False)
        batch_op.create_foreign_key("fk_expenses_department_id_departments", "departments", ["department_id"], ["id"])
        batch_op.create_foreign_key("fk_expenses_vendor_id_vendors", "vendors", ["vendor_id"], ["id"])
        batch_op.create_foreign_key(
            "fk_expenses_dept_head_reviewer_user_id_users",
            "users",
            ["dept_head_reviewer_user_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_expenses_org_owner_approver_user_id_users",
            "users",
            ["org_owner_approver_user_id"],
            ["id"],
        )

    with op.batch_alter_table("documents", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("department_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("linked_expense_type", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("linked_expense_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_documents_department_id", ["department_id"], unique=False)
        batch_op.create_foreign_key("fk_documents_department_id_departments", "departments", ["department_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("documents", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_documents_department_id_departments", type_="foreignkey")
        batch_op.drop_index("ix_documents_department_id")
        batch_op.drop_column("linked_expense_id")
        batch_op.drop_column("linked_expense_type")
        batch_op.drop_column("department_id")

    with op.batch_alter_table("expenses", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_expenses_org_owner_approver_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_expenses_dept_head_reviewer_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_expenses_vendor_id_vendors", type_="foreignkey")
        batch_op.drop_constraint("fk_expenses_department_id_departments", type_="foreignkey")
        batch_op.drop_index("ix_expenses_org_owner_approver_user_id")
        batch_op.drop_index("ix_expenses_dept_head_reviewer_user_id")
        batch_op.drop_index("ix_expenses_vendor_id")
        batch_op.drop_index("ix_expenses_department_id")
        batch_op.drop_column("payment_status")
        batch_op.drop_column("rejection_reason")
        batch_op.drop_column("org_owner_approver_user_id")
        batch_op.drop_column("dept_head_reviewer_user_id")
        batch_op.drop_column("expense_type")
        batch_op.drop_column("vendor_id")
        batch_op.drop_column("department_id")

    with op.batch_alter_table("budgets", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_budgets_department_id_departments", type_="foreignkey")
        batch_op.drop_index("ix_budgets_department_id")
        batch_op.drop_column("year")
        batch_op.drop_column("month")
        batch_op.drop_column("scope")
        batch_op.drop_column("department_id")

    op.drop_index("ix_ai_chat_messages_organization_id", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")
    op.drop_index("ix_ai_chat_sessions_organization_id", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")
    op.drop_index("ix_payment_priorities_expense_id", table_name="payment_priorities")
    op.drop_index("ix_payment_priorities_organization_id", table_name="payment_priorities")
    op.drop_table("payment_priorities")
    op.drop_index("ix_spend_limits_organization_id", table_name="spend_limits")
    op.drop_table("spend_limits")
    op.drop_index("ix_recurring_expense_requests_organization_id", table_name="recurring_expense_requests")
    op.drop_table("recurring_expense_requests")
    op.drop_index("ix_recurring_expenses_organization_id", table_name="recurring_expenses")
    op.drop_table("recurring_expenses")
    op.drop_index("ix_vendors_organization_id", table_name="vendors")
    op.drop_table("vendors")
