# Services Layout

`spendpilot-services` now contains four runnable application entrypoints:

- `app.main:app` for combined local development
- `services/identity/` for the identity deployment
- `services/finance/` for the finance deployment
- `services/documents/` for the documents deployment

The deployable services share one internal Python package so auth, database models, migrations, and runtime configuration stay aligned while each service ships as its own image.
