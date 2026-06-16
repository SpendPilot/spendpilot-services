from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rbac import ROLE_DEPT_HEAD, ROLE_EMPLOYEE, ROLE_ORG_OWNER, ROLE_PLATFORM_ADMIN, derive_highest_role, normalize_role
from app.models import Department, ExpenseCategory, Organization, OrganizationMembership, User, UserSession

MICROSOFT_CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"
PERSONAL_ACCOUNT_TENANT_PREFIX = "msa"

DEFAULT_CATEGORIES = [
    ("travel", "Travel"),
    ("meals", "Meals"),
    ("software", "Software"),
    ("office", "Office Supplies"),
    ("marketing", "Marketing"),
    ("professional-services", "Professional Services"),
]

DEFAULT_DEPARTMENTS = [
    ("IT", "Technology, systems, and infrastructure operations."),
    ("Marketing", "Demand generation, brand, and growth spend."),
    ("HR", "People operations, recruiting, and workplace support."),
]


@dataclass
class AuthContext:
    user: User
    organization: Organization
    membership: OrganizationMembership
    session: UserSession


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "organization"


def _org_name_from_email(email: str) -> str:
    domain = email.split("@")[-1].split(".")[0].replace("-", " ").replace("_", " ")
    return domain.title() or "Organization"


def _personal_workspace_name(payload: dict, email: str) -> str:
    display_name = str(payload.get("name") or "").strip()
    base_name = display_name or email.split("@")[0].replace(".", " ").replace("_", " ").title()
    return f"{base_name} Workspace"


def _is_consumer_tenant_account(payload: dict) -> bool:
    tenant_id = str(payload.get("tid") or "").strip().lower()
    issuer = str(payload.get("iss") or "").strip().lower()
    return tenant_id == MICROSOFT_CONSUMER_TENANT_ID or "/consumers/" in issuer


def _organization_partition_key(payload: dict, email: str) -> str:
    tenant_id = str(payload.get("tid") or "local-dev-tenant").strip()
    if not _is_consumer_tenant_account(payload):
        return tenant_id

    stable_account_key = str(payload.get("oid") or payload.get("sub") or email.strip().lower())
    digest = hashlib.sha256(stable_account_key.encode("utf-8")).hexdigest()[:24]
    return f"{PERSONAL_ACCOUNT_TENANT_PREFIX}:{digest}"


def _claims_roles(payload: dict) -> list[str]:
    raw_roles = payload.get("roles") or payload.get("role") or []
    if isinstance(raw_roles, list):
        return [str(role) for role in raw_roles]
    return [str(raw_roles)]


def _external_id_from_claims(payload: dict) -> str:
    oid = payload.get("oid") or payload.get("sub") or payload.get("email")
    tid = payload.get("tid") or "local"
    if not oid:
        raise ValueError("Authenticated token did not include a stable user identifier")
    return f"{tid}:{oid}"


def _session_times(payload: dict) -> tuple[datetime | None, datetime | None]:
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    return (
        datetime.fromtimestamp(issued_at, UTC) if issued_at else None,
        datetime.fromtimestamp(expires_at, UTC) if expires_at else None,
    )


def _default_membership_role(db: Session, organization: Organization, payload: dict) -> str:
    token_role = derive_highest_role(_claims_roles(payload))
    member_count = db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == organization.id
    ).count()
    if member_count == 0:
        return ROLE_ORG_OWNER
    if token_role == ROLE_PLATFORM_ADMIN:
        return ROLE_ORG_OWNER
    return ROLE_EMPLOYEE


def _build_unique_org_slug(db: Session, org_name: str, tenant_id: str) -> str:
    base_slug = _slugify(org_name)
    existing = db.query(Organization).filter(Organization.slug == base_slug).first()
    if existing is None:
        return base_slug
    return _slugify(f"{org_name}-{tenant_id[:8]}")


def _seed_default_categories(db: Session, organization: Organization) -> None:
    existing_codes = {
        category.code
        for category in db.query(ExpenseCategory).filter(ExpenseCategory.organization_id == organization.id).all()
    }
    for code, name in DEFAULT_CATEGORIES:
        if code in existing_codes:
            continue
        db.add(
            ExpenseCategory(
                organization_id=organization.id,
                code=code,
                name=name,
            )
        )


def ensure_default_departments(db: Session, organization: Organization) -> list[Department]:
    existing = {
        department.name.lower(): department
        for department in db.query(Department).filter(Department.organization_id == organization.id).all()
    }
    for name, description in DEFAULT_DEPARTMENTS:
        if name.lower() in existing:
            continue
        department = Department(
            organization_id=organization.id,
            name=name,
            description=description,
        )
        db.add(department)
        db.flush()
        existing[name.lower()] = department
    return list(existing.values())


def get_user_from_principal(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def sync_user_context_from_claims(
    db: Session,
    payload: dict,
    *,
    session_fingerprint: str,
    session_identifier: str,
    auth_provider: str,
    user_agent: str | None,
) -> AuthContext:
    settings = get_settings()
    email = payload.get("preferred_username") or payload.get("upn") or payload.get("email")
    if not email:
        raise ValueError("Authenticated token did not include an email address")

    email = str(email).strip()
    original_tenant_id = str(payload.get("tid") or "local-dev-tenant")
    is_platform_admin = email.lower() in settings.platform_admin_emails_list
    is_consumer_account = _is_consumer_tenant_account(payload)
    tenant_id = _organization_partition_key(payload, email)
    external_id = _external_id_from_claims(payload)
    user = db.query(User).filter(User.external_id == external_id).first()
    if user is None:
        user = User(
            external_id=external_id,
            entra_oid=payload.get("oid"),
            home_tenant_id=original_tenant_id,
            email=email,
            display_name=payload.get("name") or email.split("@")[0],
            platform_role=ROLE_PLATFORM_ADMIN if is_platform_admin else ROLE_EMPLOYEE,
        )
        db.add(user)
        db.flush()
    else:
        user.entra_oid = payload.get("oid") or user.entra_oid
        user.home_tenant_id = original_tenant_id
        user.email = email
        user.display_name = payload.get("name") or user.display_name
        if is_platform_admin:
            user.platform_role = ROLE_PLATFORM_ADMIN

    organization = db.query(Organization).filter(Organization.tenant_id == tenant_id).first()
    if organization is None:
        org_name = (
            _personal_workspace_name(payload, email)
            if is_consumer_account
            else payload.get("tenant_name") or _org_name_from_email(email)
        )
        organization = Organization(
            tenant_id=tenant_id,
            name=org_name,
            slug=_build_unique_org_slug(db, org_name, tenant_id),
            default_currency=settings.finance_default_currency,
        )
        db.add(organization)
        db.flush()
        _seed_default_categories(db, organization)
        ensure_default_departments(db, organization)
    else:
        ensure_default_departments(db, organization)

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        role = _default_membership_role(db, organization, payload)
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=role,
            onboarding_completed=role == ROLE_ORG_OWNER,
        )
        db.add(membership)
    else:
        normalized_role = normalize_role(membership.role)
        if membership.role != normalized_role:
            membership.role = normalized_role
        if membership.role == ROLE_ORG_OWNER and not membership.onboarding_completed:
            membership.onboarding_completed = True

    issued_at, expires_at = _session_times(payload)
    session = db.query(UserSession).filter(UserSession.session_fingerprint == session_fingerprint).first()
    if session is None:
        session = UserSession(
            session_fingerprint=session_fingerprint,
            session_identifier=session_identifier,
            user_id=user.id,
            organization_id=organization.id,
            auth_provider=auth_provider,
            user_agent=user_agent,
            claims_json=payload,
            issued_at=issued_at,
            expires_at=expires_at,
            last_seen_at=datetime.now(UTC),
        )
        db.add(session)
    else:
        session.user_id = user.id
        session.organization_id = organization.id
        session.user_agent = user_agent
        session.claims_json = payload
        session.issued_at = issued_at
        session.expires_at = expires_at
        session.last_seen_at = datetime.now(UTC)

    db.commit()
    db.refresh(user)
    db.refresh(organization)
    db.refresh(membership)
    db.refresh(session)

    if session.revoked_at is not None:
        raise ValueError("This session has been revoked")

    return AuthContext(
        user=user,
        organization=organization,
        membership=membership,
        session=session,
    )


def list_memberships(db: Session, organization_id: str) -> list[OrganizationMembership]:
    return (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == organization_id)
        .order_by(OrganizationMembership.created_at.asc())
        .all()
    )


def list_departments(db: Session, organization_id: str) -> list[Department]:
    return (
        db.query(Department)
        .filter(Department.organization_id == organization_id)
        .order_by(Department.name.asc())
        .all()
    )


def get_membership_within_organization(db: Session, organization_id: str, membership_id: str) -> OrganizationMembership | None:
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization_id,
        )
        .first()
    )


def get_department_within_organization(db: Session, organization_id: str, department_id: str) -> Department | None:
    return (
        db.query(Department)
        .filter(
            Department.id == department_id,
            Department.organization_id == organization_id,
        )
        .first()
    )


def get_department_head_membership(
    db: Session,
    organization_id: str,
    department_id: str,
    *,
    exclude_membership_id: str | None = None,
) -> OrganizationMembership | None:
    query = db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.department_id == department_id,
        OrganizationMembership.role == ROLE_DEPT_HEAD,
        OrganizationMembership.status == "active",
    )
    if exclude_membership_id:
        query = query.filter(OrganizationMembership.id != exclude_membership_id)
    return query.first()


def assign_membership_department(
    db: Session,
    organization_id: str,
    membership_id: str,
    department_id: str,
) -> OrganizationMembership | None:
    membership = get_membership_within_organization(db, organization_id, membership_id)
    department = get_department_within_organization(db, organization_id, department_id)
    if membership is None or department is None:
        return None
    membership.department_id = department.id
    membership.onboarding_completed = True
    db.commit()
    db.refresh(membership)
    return membership


def list_sessions(db: Session, organization_id: str) -> list[UserSession]:
    return (
        db.query(UserSession)
        .filter(UserSession.organization_id == organization_id)
        .order_by(UserSession.last_seen_at.desc().nullslast())
        .all()
    )


def revoke_session(db: Session, session_id: str) -> UserSession | None:
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if session is None:
        return None
    session.revoked_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return session
