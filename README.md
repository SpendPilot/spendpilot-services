# Backend

The backend is a shared FastAPI codebase with four entrypoints:

- `app.main:app` for local combined development
- `app.service_apps.identity:app` for auth, sessions, org admin, and tenant bootstrap
- `app.service_apps.finance:app` for budgets, expenses, approvals, and dashboard data
- `app.service_apps.documents:app` for uploads, scans, OCR, invoice extraction, and AI analysis

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

Each backend deployment uses the same image with a different `APP_MODULE`:

- `app.service_apps.identity:app`
- `app.service_apps.finance:app`
- `app.service_apps.documents:app`
