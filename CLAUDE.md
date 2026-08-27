# Homebase — Claude Instructions

## Architecture & Code Quality Principles

These rules apply to all new code and modifications in this codebase. Adapted
from the `ledger_finance` app's conventions.

### Module Structure

```
app/
  maintenance_calc.py     # Pure due-date math (add_interval, compute_next_due, due_bucket)
  category_templates_data.py  # Seed data: category -> default tasks/consumables/pro-service interval
  template_service.py     # Applies a category template to a newly created appliance
  document_service.py     # Document storage + entity linking (save/fetch/unlink) — the
                           #   only module that touches Document/DocumentLink directly
  context_export_service.py  # Builds the Markdown context export
  cli.py                  # `flask create-user`, `flask seed-templates`
  routes/                 # Request handlers split by domain (sub-package)
    __init__.py           # Blueprint + sub-module imports
    helpers.py            # Shared route utilities (household scoping, slugify, parse_date)
    auth.py, dashboard.py, appliances.py, documents.py,
    maintenance.py, consumables.py, service_records.py, home.py, export.py
  models.py                # SQLAlchemy ORM models
```

### SOLID & Modularity Rules

**Single Responsibility**: Each module has one job.
- Route handlers only handle HTTP: parse request → call service/model → return response
- `template_service.py` contains the one piece of cross-cutting business logic
  (applying a category template); anything similar belongs in its own service
  module, not inline in a route
- Models are thin: no business logic beyond simple property accessors
  (e.g. `Appliance.pro_service_next_due`)
- `maintenance_calc.py` has zero Flask/DB imports — keep all due-date math there,
  unit-testable in isolation

**DRY**: Before adding code, check for an existing utility:
- Household-scoped fetch-or-404 → `app/routes/helpers.get_household_appliance_or_404()`
- Date parsing from HTML `<input type="date">` → `app/routes/helpers.parse_date()`
- Category slug generation → `app/routes/helpers.slugify()`
- Due-date math → `app/maintenance_calc.py` (`add_interval`, `compute_next_due`, `due_bucket`)
- Creating/fetching/deleting a document (appliance- or home-attached) →
  `app/document_service.py` (`save_and_link`, `get_documents_for`,
  `unlink_and_maybe_delete`) — never construct `Document`/`DocumentLink`
  rows directly in a route

**Dependency Direction**: Routes → Services → Models. Never import routes from
services or models.

**Household scoping**: Every query for an appliance-owned resource
(maintenance task, consumable, service record) must go through
`get_household_appliance_or_404()` (directly or via the resource's own
`appliance_id`) so one household can never read or modify another's data —
there is no other access-control layer in this app. A `Document` isn't
owned by an appliance directly (see `DocumentLink` in `models.py`), but it
always carries its own `household_id` — check that instead when scoping
access to one directly (see `document_file` in `routes/documents.py`).

**New Route Domains**: Add routes to the appropriate sub-module in
`app/routes/`. If none fits, create a new sub-module and register it in
`app/routes/__init__.py`.

### What NOT to Do
- Do not add business logic to route handlers — extract to a service or a
  model property
- Do not duplicate due-date math — import from `app/maintenance_calc.py`
- Do not add new module-level mutable globals — use class instances or app config
- Do not silently swallow exceptions in service error paths — callers should decide
- Do not skip the household-scoping helper "just this once" on a new route

---

## Pre-Commit Clean Code Pass

Before creating any commit, run a clean code pass over all changed files.

### SOLID & DRY
- Does any new function duplicate logic that already exists elsewhere? Search
  `app/routes/helpers.py`, `app/maintenance_calc.py`, and adjacent route
  modules before writing new code.
- Does any route handler contain business logic that belongs in a service or
  model property?

### Readability & Comments
- Remove any docstring or comment that describes WHAT the code does —
  well-named identifiers do that already.
- Keep only comments that explain a non-obvious WHY: a hidden constraint, a
  subtle invariant, a workaround, or a surprising omission.
- Prefer one-liner docstrings over multi-line blocks.

### Test Coverage
- Every new route needs at least: resource-not-found (404, via household
  scoping), invalid input, and success cases.
- Every new pure function in `maintenance_calc.py` needs unit tests covering
  its edge cases (boundary dates, missing/None inputs).
- Do not add tests that exercise the same code path twice under different names.

### Run the test suite
```bash
.venv/bin/python -m pytest tests/ -q
```
All tests must pass before committing.

---

## Database Migrations

Back up `data/homebase.db` before running a migration in a real deployment
(there is no automated backup script yet — copy the file manually):

```bash
cp data/homebase.db data/homebase.db.bak
flask db upgrade
```

To add a new migration after changing `app/models.py`:

```bash
FLASK_APP=run.py flask db migrate -m "describe the change"
FLASK_APP=run.py flask db upgrade
```
