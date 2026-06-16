from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.rbac import ROLE_DEPT_HEAD, ROLE_ORG_OWNER, ROLE_PLATFORM_ADMIN, normalize_role
from app.core.security import require_role
from app.db.session import get_db
from app.models import OrganizationMembership
from app.schemas.auth import DepartmentOut, MembershipOut, MembershipRoleUpdateRequest, OrganizationOut, SessionOut
from app.schemas.common import APIEnvelope
from app.services.user_service import (
    get_department_head_membership,
    get_department_within_organization,
    get_membership_within_organization,
    list_departments,
    list_sessions,
    revoke_session,
)

router = APIRouter()


@router.get("/organization", response_model=APIEnvelope[OrganizationOut])
def get_current_organization(principal=Depends(require_role(ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER))) -> APIEnvelope[OrganizationOut]:
    return APIEnvelope(
        data=OrganizationOut(
            id=principal.organization_id,
            tenant_id=principal.tenant_id or "",
            name=principal.organization_name,
            slug=principal.organization_slug,
            default_currency=principal.default_currency,
        )
    )


@router.get("/members", response_model=APIEnvelope[list[MembershipOut]])
def members(
    principal=Depends(require_role(ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER)),
    db: Session = Depends(get_db),
) -> APIEnvelope[list[MembershipOut]]:
    memberships = (
        db.query(OrganizationMembership)
        .options(joinedload(OrganizationMembership.user), joinedload(OrganizationMembership.department))
        .filter(OrganizationMembership.organization_id == principal.organization_id)
        .order_by(OrganizationMembership.created_at.asc())
        .all()
    )
    return APIEnvelope(data=[MembershipOut.model_validate(item) for item in memberships])


@router.get("/departments", response_model=APIEnvelope[list[DepartmentOut]])
def departments(
    principal=Depends(require_role(ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER)),
    db: Session = Depends(get_db),
) -> APIEnvelope[list[DepartmentOut]]:
    return APIEnvelope(data=[DepartmentOut.model_validate(item) for item in list_departments(db, principal.organization_id)])


@router.patch("/members/{membership_id}", response_model=APIEnvelope[MembershipOut])
def update_member(
    membership_id: str,
    payload: MembershipRoleUpdateRequest,
    principal=Depends(require_role(ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER)),
    db: Session = Depends(get_db),
) -> APIEnvelope[MembershipOut]:
    membership = get_membership_within_organization(db, principal.organization_id, membership_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    if membership.user_id == principal.user_id and payload.status == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own membership")

    next_role = normalize_role(payload.role) if payload.role is not None else normalize_role(membership.role)
    next_status = payload.status or membership.status
    next_department_id = payload.department_id if payload.department_id is not None else membership.department_id

    if membership.role == ROLE_ORG_OWNER and next_role != ROLE_ORG_OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The organization owner role cannot be reassigned in Phase 1")

    if next_role == ROLE_ORG_OWNER and membership.role != ROLE_ORG_OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only the bootstrap org owner is supported in Phase 1")

    if next_status not in {"active", "inactive"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid membership status")

    if next_department_id is not None:
        if get_department_within_organization(db, principal.organization_id, next_department_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    if next_role == ROLE_DEPT_HEAD:
        if next_department_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A department head must be assigned to a department")
        existing_head = get_department_head_membership(
            db,
            principal.organization_id,
            next_department_id,
            exclude_membership_id=membership.id,
        )
        if existing_head is not None and next_status == "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That department already has an active department head")

    membership.role = next_role
    membership.status = next_status
    membership.department_id = next_department_id
    membership.onboarding_completed = membership.role == ROLE_ORG_OWNER or membership.department_id is not None
    db.commit()
    membership = (
        db.query(OrganizationMembership)
        .options(joinedload(OrganizationMembership.user), joinedload(OrganizationMembership.department))
        .filter(OrganizationMembership.id == membership.id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found after update")
    return APIEnvelope(data=MembershipOut.model_validate(membership))


@router.get("/sessions", response_model=APIEnvelope[list[SessionOut]])
def sessions(
    principal=Depends(require_role(ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER)),
    db: Session = Depends(get_db),
) -> APIEnvelope[list[SessionOut]]:
    return APIEnvelope(data=[SessionOut.model_validate(item) for item in list_sessions(db, principal.organization_id)])


@router.post("/sessions/{session_id}/revoke", response_model=APIEnvelope[SessionOut])
def revoke(
    session_id: str,
    principal=Depends(require_role(ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER)),
    db: Session = Depends(get_db),
) -> APIEnvelope[SessionOut]:
    session = revoke_session(db, session_id)
    if session is None or session.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return APIEnvelope(data=SessionOut.model_validate(session))
