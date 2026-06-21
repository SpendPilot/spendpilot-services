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
- Async email notifications through Azure Service Bus and an Azure Function sender
- Azure Blob Storage uploads
- Azure AI Document Intelligence invoice extraction
- Azure AI Foundry analysis with fallback heuristics

## Local checks

```bash
pytest
```

## Async email flow

The repo now includes asynchronous notification wiring for:

- `WELCOME_EMAIL`
- `PASSWORD_RESET`
- `EXPENSE_SUBMITTED`
- `EXPENSE_APPROVED`
- `EXPENSE_REJECTED`

Runtime flow:

1. The backend publishes a JSON payload to the `email-requests` Service Bus queue.
2. The Azure Function in [`functions/email_sender`](./functions/email_sender) consumes the message.
3. Azure Communication Services Email sends the rendered message.

Backend configuration:

- `EMAIL_NOTIFICATIONS_ENABLED`
- `AZURE_SERVICE_BUS_FULLY_QUALIFIED_NAMESPACE`
- `AZURE_SERVICE_BUS_QUEUE_NAME`
- `AZURE_SERVICE_BUS_CONNECTION_STRING` for optional local overrides

Function configuration:

- `SERVICEBUS_CONNECTION__fullyQualifiedNamespace`
- `EMAIL_SERVICE_BUS_QUEUE_NAME`
- `ACS_EMAIL_CONNECTION_STRING` or `ACS_EMAIL_ENDPOINT`
- `ACS_EMAIL_SENDER_ADDRESS`

## Service split in AKS

Each backend deployment now builds its own image from its own service folder:

- `services/identity/Dockerfile`
- `services/finance/Dockerfile`
- `services/documents/Dockerfile`

All three images still share the same internal Python package, database models, and Alembic migrations so runtime behavior stays aligned across the split.
