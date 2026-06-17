# Backend

The backend is organized as three deployable service folders plus one combined local-development app:

- `app.main:app` for local combined development
- `services/identity/service_app.py` for auth, sessions, org admin, and tenant bootstrap
- `services/finance/service_app.py` for budgets, expenses, approvals, and dashboard data
- `services/documents/service_app.py` for uploads, scans, OCR, invoice extraction, and AI analysis

Core capabilities:

- Microsoft Entra access token validation with multi-tenant support
- Tenant-aware RBAC and organization membership bootstrap
- Session persistence and session revocation
- Finance entities: categories, budgets, expenses, approvals, audit events
- Azure Blob Storage uploads
- Azure AI Document Intelligence invoice extraction
- Azure AI Foundry analysis with fallback heuristics

## Local checks

```bash
pytest
```

## Service split in AKS

Each backend deployment now builds its own image from its own service folder:

- `services/identity/Dockerfile`
- `services/finance/Dockerfile`
- `services/documents/Dockerfile`

All three images still share the same internal Python package, database models, and Alembic migrations so runtime behavior stays aligned across the split.
