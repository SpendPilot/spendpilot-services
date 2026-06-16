from datetime import datetime

from pydantic import BaseModel, EmailStr


class OrganizationOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    slug: str
    default_currency: str

    model_config = {"from_attributes": True}


class DepartmentOut(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class MembershipOut(BaseModel):
    id: str
    organization_id: str
    user_id: str
    department_id: str | None
    role: str
    status: str
    cost_center: str | None
    onboarding_completed: bool
    department: DepartmentOut | None = None
    user: "UserOut | None" = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    external_id: str
    entra_oid: str | None
    home_tenant_id: str | None
    email: EmailStr
    display_name: str
    platform_role: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    id: str
    session_identifier: str
    auth_provider: str
    user_agent: str | None
    issued_at: datetime | None
    expires_at: datetime | None
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuthProfileOut(BaseModel):
    user: UserOut
    organization: OrganizationOut
    membership: MembershipOut
    session: SessionOut
    effective_role: str


class DevLoginRequest(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = None
    role: str | None = None
    tenant_id: str | None = None


class MembershipRoleUpdateRequest(BaseModel):
    role: str | None = None
    department_id: str | None = None
    status: str | None = None


class DepartmentSelectionRequest(BaseModel):
    department_id: str


class AuthResponse(BaseModel):
    access_token: str
    profile: AuthProfileOut


MembershipOut.model_rebuild()
