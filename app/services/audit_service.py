from sqlalchemy.orm import Session

from app.models import AuditEvent


def create_audit_event(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str | None,
    resource_type: str,
    resource_id: str,
    action: str,
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        details_json=details,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
