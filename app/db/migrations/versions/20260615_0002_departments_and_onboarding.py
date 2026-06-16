"""Add departments, onboarding state, and canonical membership roles

Revision ID: 20260615_0002
Revises: 20260604_0001
Create Date: 2026-06-15 00:00:00
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "20260615_0002"
down_revision = "20260604_0001"
branch_labels = None
depends_on = None


department_table = sa.table(
    "departments",
    sa.column("id", sa.String(length=36)),
    sa.column("organization_id", sa.String(length=36)),
    sa.column("name", sa.String(length=100)),
    sa.column("description", sa.String(length=255)),
)

organization_table = sa.table(
    "organizations",
    sa.column("id", sa.String(length=36)),
)


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_department_name"),
    )
    op.create_index("ix_departments_organization_id", "departments", ["organization_id"], unique=False)

    with op.batch_alter_table("organization_memberships", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("department_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        batch_op.create_index("ix_organization_memberships_department_id", ["department_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_organization_memberships_department_id_departments",
            "departments",
            ["department_id"],
            ["id"],
        )

    bind = op.get_bind()
    organizations = list(bind.execute(sa.select(organization_table.c.id)))
    default_departments = [
        ("IT", "Technology, systems, and infrastructure operations."),
        ("Marketing", "Demand generation, brand, and growth spend."),
        ("HR", "People operations, recruiting, and workplace support."),
    ]
    for organization in organizations:
        for name, description in default_departments:
            bind.execute(
                department_table.insert().values(
                    id=str(uuid.uuid4()),
                    organization_id=organization.id,
                    name=name,
                    description=description,
                )
            )

    bind.execute(
        sa.text(
            """
            UPDATE organization_memberships
            SET role = CASE
                WHEN role = 'org_admin' THEN 'org_owner'
                WHEN role IN ('finance_manager', 'approver') THEN 'dept_head'
                WHEN role = 'auditor' THEN 'employee'
                ELSE role
            END
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE organization_memberships
            SET onboarding_completed = 1
            WHERE role = 'org_owner'
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("organization_memberships", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_organization_memberships_department_id_departments", type_="foreignkey")
        batch_op.drop_index("ix_organization_memberships_department_id")
        batch_op.drop_column("onboarding_completed")
        batch_op.drop_column("department_id")
    op.drop_index("ix_departments_organization_id", table_name="departments")
    op.drop_table("departments")
