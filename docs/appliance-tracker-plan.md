# Home Appliance Maintenance Tracker — Architecture & Build Plan

## Context

The user currently tracks appliance make/model/serial numbers, manuals, and
maintenance schedules in a hand-built spreadsheet (photographing rating
plates, researching service intervals by hand). It works but doesn't scale,
has no reminders, and isn't shared with their spouse. The goal is a small
web app that replaces the spreadsheet: an appliance inventory with attached
photos/manuals, homeowner-maintenance + consumable-replacement + pro-service
tracking with due-date logic, a dashboard, and email reminders.

This is explicitly a single-household tool (not multi-tenant SaaS), and the
user asked for it to be built like their existing `ledger_finance` app
(`panderson54/ledger_finance`): Python backend, Bootstrap frontend, SQL
database. That repo was cloned and inspected as the reference pattern — the
plan below intentionally mirrors its structure, conventions, and deployment
model rather than inventing new ones, and calls out the handful of places
where the new app must depart from it (multi-user auth, file uploads,
scheduled reminders — none of which exist in `ledger_finance` today).

This `homebase` repo was empty at the time of planning (just a placeholder
README), so it is the natural home for this app unless the user says
otherwise — see the open questions at the end.

Decisions already made with the user:
- **Hosting**: self-hosted on a Raspberry Pi, same as `ledger_finance`
  (Docker Compose or Nginx+Gunicorn+systemd).
- **File storage**: local disk volume (mirrors `ledger_finance`'s `./data`
  bind-mount pattern), not S3/R2.
- **Email reminders**: sent via Gmail SMTP with an app password.

## Reference patterns from `ledger_finance` to reuse directly

(Paths below are in `panderson54/ledger_finance`.)

- **App factory + extension init** — `app/__init__.py`: `create_app()`,
  `db = SQLAlchemy()`, `Migrate()`, `CSRFProtect()`, WAL-mode SQLite via an
  `Engine.connect` event listener, `.env` via `python-dotenv`, rotating
  file logging (`app.log` / `error.log`) with an `after_request` logger and
  a global 500 handler. Copy this file's shape almost verbatim.
- **Routes-as-blueprint-package** — `app/routes/__init__.py` defines
  `main_bp`; each domain gets its own submodule (`accounts.py`,
  `snapshots.py`, etc.) that imports `main_bp` and registers routes on it.
  `app/routes/helpers.py` holds `_bad_request(msg)` / `_not_found(resource)`
  returning `{'error': ...}`, and does **not** import `main_bp` (avoids
  circular imports).
- **Routes → Services → Models** dependency rule, thin models with only
  `@property` accessors, pure framework-free math modules for anything
  calculation-heavy (`dividend_calc.py`, `projections.py` are the model —
  the appliance app's due-date math belongs in an equivalent pure module).
- **`app_settings` key/value table** (`app/models.py`) — reuse this exact
  pattern for reminder lead-time, SMTP config, etc., instead of a migration
  per config knob.
- **`base.html`** template — shared navbar, Bootstrap 5 confirm-modal
  helper (`showConfirmModal`), dark/light theme toggle via `localStorage`,
  CSRF-token auto-injection into `fetch()`. Copy wholesale as the new app's
  base layout.
- **Deployment** — `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`
  (`flask db upgrade` then `exec gunicorn ...`), and the README's
  Raspberry-Pi Nginx+Gunicorn+systemd walkthrough. Reuse the same shape,
  new port.
- **`CLAUDE.md`** — the SOLID/DRY module-structure doc, error-response
  convention, logging convention, and pre-commit clean-code/test-coverage
  checklist. Port this into the new repo, adapted to the new module names.
- **Testing** — `pytest` + `pytest-flask` + `pytest-cov`, `tests/conftest.py`
  pattern (`DATABASE_URL=sqlite:///:memory:` set **before** importing `app`,
  `StaticPool`, per-test row teardown, shared factory fixtures).
- **Background-thread-with-job-id** pattern from
  `app/routes/brokerage_import.py` (in-memory job dict + polling endpoint)
  is the closest existing precedent for async work — useful for the
  "extract text from photo" OCR call (calling Claude vision synchronously
  is simpler and fine at this scale; keep the threaded pattern in mind only
  if OCR calls turn out to be slow enough to need a spinner).
- **`ai_utils.py`** — shared Claude API client/model-constant pattern to
  copy for the new app's OCR and manual-lookup service modules.

Deliberate departures from `ledger_finance`:
- **Auth**: `ledger_finance` has none (LAN/VPN-only, explicit
  single-user design). This app needs at least two named users (the
  household) with their own login, since "not accessible to my spouse" is
  a stated problem to solve — add `Flask-Login` + `werkzeug.security`
  password hashing + a `users` table, but keep it minimal: no self-serve
  signup, no email verification, no password reset flow for v1 — accounts
  are created by hand (a `flask create-user` CLI command) since there are
  only ever a handful of users.
- **File uploads persisted to disk**: `ledger_finance` never writes
  uploaded files to disk (CSVs are parsed in-memory). This app needs to
  actually store photos and PDFs. Use a `./data/uploads/<household_id>/`
  disk layout (mirrors the existing `./data` bind-mount), validate
  extension + size + re-encode images with Pillow (already a dependency in
  `ledger_finance`) before saving, and store the relative path + original
  filename + content type in a `documents` row.
- **Scheduled reminders**: `ledger_finance` has no in-app scheduler — its
  only recurring job is `scripts/auto_update.sh` run by a systemd timer at
  the OS level. Follow that same convention rather than an in-process
  scheduler (avoids duplicate firing across Gunicorn's multiple workers):
  a standalone `scripts/send_reminders.py` that queries due/overdue items
  and sends one digest email per user, invoked daily by a systemd timer
  (or `cron`) alongside the existing `ledger-update.timer`-style unit.

## Tech stack

- **Backend**: Flask 3, Flask-SQLAlchemy, Flask-Migrate (Alembic),
  Flask-WTF (CSRF), Flask-Login, gunicorn — exactly `ledger_finance`'s
  stack plus Flask-Login.
- **DB**: SQLite in WAL mode, same as `ledger_finance` — fine for a
  household of 2-3 users and a low write rate; leaves a clean upgrade path
  to Postgres later (SQLAlchemy already abstracts this) if this ever
  becomes multi-household.
- **Frontend**: server-rendered Jinja2 templates + Bootstrap 5 via CDN, no
  JS framework/build step — copy `base.html` and its JS helpers directly.
- **Photo/label OCR (phase 3)**: Anthropic Claude vision (multimodal
  message with an image block) via the `anthropic` SDK, following the
  `ai_utils.py` client/constant pattern from `ledger_finance`.
- **Manual auto-lookup (phase 4)**: Claude with web search to propose a
  candidate manual URL for a given make+model, presented to the user to
  confirm/replace — same "AI service module, user confirms before saving"
  shape as `ledger_finance`'s ticker classification.
- **Email**: `smtplib` + Gmail SMTP with an app password, no third-party
  email service.
- **Deployment**: Docker Compose (or Nginx+Gunicorn+systemd) on the same
  Raspberry Pi as `ledger_finance`, on a different port; a systemd timer
  for the daily reminder script.
- **Testing**: pytest, same `conftest.py` in-memory-SQLite pattern.

## Data model

Builds on the shape from the original prompt; concretized against
SQLAlchemy models and the reference appliances table.

- `households(id, name)` — exists from day one even though there's one row,
  so nothing has to be retrofitted if this opens up later.
- `users(id, household_id FK, email, password_hash, name)`
- `appliances(id, household_id FK, category, make, model_number, serial_number, location, install_date, purchase_date, status[active/archived], notes, created_at)`
- `documents(id, appliance_id FK, doc_type[photo/manual/receipt/other], file_path, external_url, original_filename, content_type, uploaded_at)`
  — `file_path` XOR `external_url`, either a local upload or a link. One
  typed table for photos, manuals, and receipts rather than a separate
  join table per document type — matches "multiple documents per
  appliance" without extra structure.
- `maintenance_tasks(id, appliance_id FK, title, description, frequency_value, frequency_unit[days/weeks/months/years], last_completed_at, next_due_at, active)`
- `maintenance_logs(id, task_id FK, completed_at, completed_by_user_id FK, notes)`
- `consumables(id, appliance_id FK, name, part_number, purchase_url, frequency_value, frequency_unit, last_replaced_at, next_due_at)`
- `appliances.pro_service_interval_value/unit` — the recommended cadence,
  set once per appliance (not per visit).
- `service_records(id, appliance_id FK, service_date, vendor, notes, cost)`
  — pure visit history; `next_due_at` is computed from the latest record's
  `service_date` + the appliance's interval, not stored per-record.
- `category_templates(id, category, task_title, task_description, frequency_value, frequency_unit, kind[maintenance/consumable], part_number_hint)`
  — seed data (loaded by a `flask seed-templates` command, not a UI), keyed
  by `category` string; applying a template on appliance creation just
  copies matching rows into `maintenance_tasks`/`consumables`.
- `app_settings(household_id FK, key, value)` — reminder lead-time (days),
  SMTP "from" address, etc.

Due-date computation (`next_due_at`) is pure math (`date last + frequency`
→ store on write, matching `ledger_finance`'s "calculated_metrics
recomputed on write" convention) — implement as a framework-free helper
module, unit-testable without Flask/DB, e.g. `app/maintenance_calc.py`.

Sanity-checked against the 7 reference appliances (furnace, water heater,
dishwasher, refrigerator, dehumidifier, mini-split outdoor/indoor):
`category_templates` seeded for each of those 7 categories covers all of
them; the mini-split outdoor unit and dehumidifier correctly end up with
zero consumables, and the dishwasher/refrigerator correctly end up with no
pro-service interval — the schema doesn't force either to exist.

## Phased build plan

**Phase 1 — Core inventory + manual tracking (smallest usable v1)**
- Flask app skeleton mirroring `ledger_finance`'s layout; `households`,
  `users` (Flask-Login, hand-created accounts), `appliances`, `documents`
  (manual upload + external link only, no OCR yet), `maintenance_tasks` +
  `maintenance_logs`, `consumables`, `service_records`.
- CRUD UI: add/edit/archive appliance, attach documents, add/complete
  maintenance tasks and consumables, log service visits.
- Dashboard: overdue / due-soon / up-to-date across all appliances and
  consumables, pro-service due dates visually distinguished.
- `category_templates` seed data + "apply template on create" flow for the
  7 reference categories.
- Deploy to the Pi via Docker Compose, next to `ledger_finance`.

**Phase 2 — Reminders**
- `app_settings`-backed reminder lead time.
- `scripts/send_reminders.py` + systemd timer, Gmail SMTP digest email per
  user covering overdue + due-within-lead-time items.

**Phase 3 — Photo OCR**
- Label-photo upload flow extracts make/model/serial via Claude vision,
  pre-fills the add-appliance form, user reviews/corrects before saving.

**Phase 4 — Manual auto-lookup (stretch)**
- Claude + web search suggests a manual URL from make+model; user
  confirms/replaces before it's saved as a `documents` row.

## Verification

- `pytest tests/ -q` (mirroring `ledger_finance`'s `pytest.ini` /
  `conftest.py` in-memory SQLite setup) covering: due-date math module
  (unit tests, no DB), route-level 404/400/200 cases per the `CLAUDE.md`
  checklist, template-application seeding logic, reminder-query logic
  (given fixture data matching the 7 reference appliances, assert correct
  overdue/due-soon/ok buckets).
- Manual end-to-end pass in a browser: add each of the 7 reference
  appliances, confirm templates seed sensible tasks/consumables, mark a
  task done and confirm `next_due_at` advances correctly, upload a photo
  and a manual PDF, log a service visit, and (once Phase 2 lands) trigger
  `scripts/send_reminders.py` manually and confirm the email arrives with
  correct due items.
- `docker compose up --build` locally before deploying to the Pi, same as
  `ledger_finance`'s dev workflow.

## Open questions for the user

1. Build this app in `homebase` (currently empty) as planned above, or in
   a differently-named new repo?
2. Should this app share the Pi host with `ledger_finance` but stay fully
   independent (separate containers/ports/DBs, as planned above), or is
   there any desire to eventually consolidate auth/hosting across
   household apps?
3. Any preference on the exact category list beyond the 7 reference
   appliances (e.g. garage door opener, sump pump, washer/dryer) to seed
   `category_templates` for at launch, or is it fine to add categories
   ad hoc as new appliances are entered?
