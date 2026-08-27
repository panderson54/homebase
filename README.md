# Homebase

A small household appliance maintenance tracker: one place for appliance
make/model/serial numbers, manuals, photos of rating plates, homeowner
maintenance checklists, consumable replacement schedules, and professional
service history — with a dashboard showing what's overdue or due soon.

Built for a single household (you and anyone you share it with), not as
multi-tenant SaaS. See `docs/appliance-tracker-plan.md` for the full
architecture/build plan this was scaffolded from.

## Features (v1)

- Appliance inventory: name, category, make, model, serial, location,
  install/purchase dates, notes, archive without losing history
- Documents: upload photos/manuals/receipts (stored on local disk) or link
  to an external URL, multiple per appliance
- Homeowner maintenance tasks with a frequency; "mark done" logs the
  completion and recomputes the next due date
- Consumables (filters, anode rods, etc.) tracked the same way, with an
  optional part number and purchase link
- Professional service: a recommended interval per appliance, a log of
  actual visits (date/vendor/notes/cost), and a computed next-due date
- A dashboard of overdue / due-soon / up-to-date items across the whole
  household, with professional-service items visually distinguished
- Category templates: adding a "furnace" (or the other 6 reference
  categories) pre-fills its usual maintenance tasks, consumables, and
  service interval — customizable afterward
- Simple multi-user login (Flask-Login) — accounts are created by hand via
  a CLI command, no self-serve signup

Not in v1 (see the build plan for the phased rollout): email reminders,
photo OCR for auto-filling make/model/serial, and automatic manual lookup.

## Tech stack

Flask 3 + Flask-SQLAlchemy + Flask-Migrate (Alembic) + Flask-Login +
Flask-WTF (CSRF), SQLite (WAL mode), server-rendered Jinja2 templates with
Bootstrap 5 (no JS build step), gunicorn. Modeled on the `ledger_finance`
app's structure and deployment approach.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env   # fill in SECRET_KEY at minimum

FLASK_APP=run.py .venv/bin/flask db upgrade
FLASK_APP=run.py .venv/bin/flask seed-templates
FLASK_APP=run.py .venv/bin/flask create-user   # prompts for email/name/password

.venv/bin/python run.py   # http://localhost:5100
```

### Running tests

```bash
.venv/bin/python -m pytest tests/ -q
```

## Project structure

```
app/
  __init__.py                 # Flask application factory
  models.py                   # SQLAlchemy models
  maintenance_calc.py         # Pure due-date math (no Flask/DB imports)
  category_templates_data.py  # Seed data per appliance category
  template_service.py         # Applies a category template to a new appliance
  cli.py                      # `flask create-user`, `flask seed-templates`
  routes/                     # Blueprint, split by domain
  templates/, static/         # Jinja2 templates, Bootstrap-based
migrations/                    # Alembic migrations
tests/                          # pytest suite (in-memory SQLite per test)
docs/appliance-tracker-plan.md  # Architecture & build plan
```

## CLI commands

- `flask create-user` — creates the household (on first run) and a user
  account; prompts for email, name, and password
- `flask seed-templates` — (re)loads `category_templates` from
  `app/category_templates_data.py`; safe to re-run, it replaces existing rows

## Deployment

### Docker Compose

```bash
cp .env.example .env   # set SECRET_KEY
docker compose up --build -d
```

The app listens on port 5100, with `./data` (SQLite DB + uploaded files) and
`./logs` bind-mounted so they persist across container rebuilds. Run the
CLI commands above via `docker compose exec homebase flask create-user`
(and `seed-templates`) once the container is up.

### Raspberry Pi (self-hosted, alongside `ledger_finance`)

Same shape as `ledger_finance`'s deployment: either the Docker Compose setup
above, or Nginx (reverse proxy + TLS/Basic Auth if exposed beyond your LAN)
in front of Gunicorn managed by a systemd unit, running on a different port
than `ledger_finance`. `entrypoint.sh` runs `flask db upgrade` automatically
before starting Gunicorn, so deploys are just "pull, rebuild, restart."

## Data model

See `docs/appliance-tracker-plan.md` for the full schema rationale. In
short: `households` → `users`, `appliances`; each appliance has
`documents`, `maintenance_tasks` (+ `maintenance_logs`), `consumables`, and
`service_records`; `category_templates` is seed data keyed by category,
copied onto a new appliance when its template is applied.
