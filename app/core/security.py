from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rbac import APPROVAL_ROLES, FINANCE_WRITE_ROLES, ORG_READ_ROLES, normalize_role
from app.db.session import get_db
from app.services.user_service import MICROSOFT_CONSUMER_TENANT_ID, sync_user_context_from_claims

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass
class AuthenticatedPrincipal:
    user_id: str
    email: str
    display_name: str
    role: str
    platform_role: str
    membership_id: str
    organization_id: str
    organization_name: str
    organization_slug: str
    default_currency: str
    membership_status: str
    department_id: str | None
    department_name: str | None
    onboarding_completed: bool
    tenant_id: str | None
    entra_oid: str | None
    session_id: str

    @property
    def can_read_org(self) -> bool:
        return self.role in ORG_READ_ROLES

    @property
    def can_write_finance(self) -> bool:
        return self.role in FINANCE_WRITE_ROLES

    @property
    def can_approve(self) -> bool:
        return self.role in APPROVAL_ROLES


class EntraTokenValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.metadata = self._resolve_metadata()
        self.issuer = self.metadata["issuer"]
        self._jwk_client = jwt.PyJWKClient(self.metadata["jwks_uri"])

    def _resolve_metadata(self) -> dict:
        config_url = f"{self.settings.authority}/v2.0/.well-known/openid-configuration"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(config_url)
            response.raise_for_status()
        payload = response.json()
        if not payload.get("jwks_uri") or not payload.get("issuer"):
            raise RuntimeError("OpenID configuration is missing required fields")
        return payload

    def validate(self, token: str) -> dict:
        signing_key = self._jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.settings.accepted_backend_audiences,
            options={"verify_iss": False},
        )
        self._validate_tenant_and_issuer(payload)
        return payload

    def _validate_tenant_and_issuer(self, payload: dict) -> None:
        tenant_id = str(payload.get("tid", "")).strip()
        issuer = str(payload.get("iss", "")).strip()
        if not tenant_id or not self._looks_like_guid(tenant_id):
            raise jwt.InvalidTokenError("Token did not include a valid tenant ID")

        if (
            self.settings.allowed_tenant_ids_list
            and tenant_id not in self.settings.allowed_tenant_ids_list
            and tenant_id != MICROSOFT_CONSUMER_TENANT_ID
        ):
            raise jwt.InvalidTokenError("Tenant is not allowed for this API")

        if "{tenantid}" in self.issuer:
            expected_issuer = self.issuer.replace("{tenantid}", tenant_id)
        else:
            expected_issuer = self.issuer
        if issuer != expected_issuer:
            raise jwt.InvalidTokenError("Token issuer was not accepted")

    @staticmethod
    def _looks_like_guid(value: str) -> bool:
        try:
            UUID(value)
            return True
        except ValueError:
            return False


@lru_cache
def get_entra_validator() -> EntraTokenValidator:
    return EntraTokenValidator(get_settings())


def create_dev_access_token(email: str, display_name: str, role: str, tenant_id: str = "local-dev-tenant") -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": email,
        "oid": f"dev-{email}",
        "tid": tenant_id,
        "email": email,
        "preferred_username": email,
        "name": display_name,
        "roles": [role],
        "aud": settings.backend_audience,
        "iss": "dev-local",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
        "sid": f"sid-{email}",
    }
    return jwt.encode(payload, settings.dev_auth_secret, algorithm="HS256")


def _decode_dev_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.dev_auth_secret,
        algorithms=["HS256"],
        audience=settings.backend_audience,
    )


def _get_token_payload(token: str, settings: Settings) -> dict:
    try:
        if settings.auth_mode == "dev-local":
            return _decode_dev_token(token)
        return get_entra_validator().validate(token)
    except jwt.InvalidTokenError as exc:
        logger.warning(
            "Token validation failed for auth mode %s with accepted audiences %s and authority %s: %s",
            settings.auth_mode,
            settings.accepted_backend_audiences,
            settings.authority,
            exc,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    settings = get_settings()
    token = credentials.credentials
    payload = _get_token_payload(token, settings)
    session_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session_identifier = str(payload.get("sid") or payload.get("uti") or payload.get("jti") or session_fingerprint[:24])
    try:
        auth_context = sync_user_context_from_claims(
            db,
            payload,
            session_fingerprint=session_fingerprint,
            session_identifier=session_identifier,
            auth_provider="dev-local" if settings.auth_mode == "dev-local" else "entra",
            user_agent=request.headers.get("user-agent"),
            workspace_mode=request.headers.get("x-spend-workspace-mode"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    effective_role = auth_context.user.platform_role
    if effective_role != "platform_admin":
        effective_role = normalize_role(auth_context.membership.role)

    if auth_context.membership.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership is inactive")

    return AuthenticatedPrincipal(
        user_id=auth_context.user.id,
        email=auth_context.user.email,
        display_name=auth_context.user.display_name,
        role=effective_role,
        platform_role=auth_context.user.platform_role,
        membership_id=auth_context.membership.id,
        organization_id=auth_context.organization.id,
        organization_name=auth_context.organization.name,
        organization_slug=auth_context.organization.slug,
        default_currency=auth_context.organization.default_currency,
        membership_status=auth_context.membership.status,
        department_id=auth_context.membership.department_id,
        department_name=auth_context.membership.department.name if auth_context.membership.department else None,
        onboarding_completed=auth_context.membership.onboarding_completed,
        tenant_id=auth_context.organization.tenant_id,
        entra_oid=auth_context.user.entra_oid,
        session_id=auth_context.session.id,
    )


def require_role(*roles: str):
    def dependency(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> AuthenticatedPrincipal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency
