# Identity Service

Deploys the SpendPilot identity surface:

- `/health`
- `/ready`
- `/api/auth/*`
- `/api/admin/*`

This service shares the common SpendPilot package in the repo root and is built with `services/identity/Dockerfile`.

Workflow trigger note: refreshed on 2026-06-17 to republish the identity image.
