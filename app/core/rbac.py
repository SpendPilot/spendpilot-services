ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_ORG_OWNER = "org_owner"
ROLE_DEPT_HEAD = "dept_head"
ROLE_EMPLOYEE = "employee"

ROLE_ORG_ADMIN = ROLE_ORG_OWNER
ROLE_FINANCE_MANAGER = ROLE_DEPT_HEAD
ROLE_APPROVER = ROLE_DEPT_HEAD
ROLE_AUDITOR = ROLE_EMPLOYEE

ALL_ROLES = {
    ROLE_PLATFORM_ADMIN,
    ROLE_ORG_OWNER,
    ROLE_DEPT_HEAD,
    ROLE_EMPLOYEE,
}

ADMIN_ROLES = {ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER}
FINANCE_WRITE_ROLES = {ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER}
APPROVAL_ROLES = {ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER, ROLE_DEPT_HEAD}
ORG_READ_ROLES = {ROLE_PLATFORM_ADMIN, ROLE_ORG_OWNER}

ROLE_ALIASES = {
    "admin": ROLE_ORG_ADMIN,
    "auditor": ROLE_AUDITOR,
    "approver": ROLE_APPROVER,
    "dept_head": ROLE_DEPT_HEAD,
    "employee": ROLE_EMPLOYEE,
    "finance_admin": ROLE_FINANCE_MANAGER,
    "finance_manager": ROLE_FINANCE_MANAGER,
    "org_admin": ROLE_ORG_ADMIN,
    "org_owner": ROLE_ORG_OWNER,
    "platform_admin": ROLE_PLATFORM_ADMIN,
    "user": ROLE_EMPLOYEE,
}


def normalize_role(raw_role: str | None) -> str:
    if not raw_role:
        return ROLE_EMPLOYEE
    return ROLE_ALIASES.get(raw_role.strip().lower(), ROLE_EMPLOYEE)


def derive_highest_role(roles: list[str] | set[str] | tuple[str, ...]) -> str:
    normalized = {normalize_role(role) for role in roles}
    for role in (
        ROLE_PLATFORM_ADMIN,
        ROLE_ORG_OWNER,
        ROLE_DEPT_HEAD,
        ROLE_EMPLOYEE,
    ):
        if role in normalized:
            return role
    return ROLE_EMPLOYEE
