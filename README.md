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
- A home info page: address, square footage, year built (with computed
  age), notes, and documents about the property itself (floor plans,
  surveys, inspection reports)
- A one-click context export (`/export`): a verbose Markdown snapshot of
  the whole household — home profile, every appliance's full history, the
  vendor directory, and paint colors — sized to fit comfortably in an LLM
  context window, viewable with a copy button or downloadable as a `.md` file
- A vendor directory: contact details and a type (HVAC, plumbing, etc.)
  per vendor, their own quotes/invoices, and a full service-visit history
  that can optionally link to a specific appliance — so "who did I use for
  X" is always answerable
- Paint colors: what was painted where, with manufacturer/color
  name/code, a hex value rendered as an actual color swatch, a product
  link, and photos — independent of appliances/vendors
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
  document_service.py         # Document storage + entity linking (appliance/home/vendor)
  vendor_service.py           # Resolves a vendor pick/quick-add for a service visit
  vendor_types_data.py        # Suggested vendor types (HVAC, plumbing, etc.)
  context_export_service.py   # Builds the Markdown context export
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
`maintenance_tasks` (+ `maintenance_logs`) and `consumables`;
`category_templates` is seed data keyed by category, copied onto a new
appliance when its template is applied.

`documents` (an uploaded file or an external link) isn't owned by any one
entity directly — a separate `document_links` table maps a document to
whatever it's attached to (`entity_type` + `entity_id`, currently
`appliance`, `home`, or `vendor`), so a document can in principle be
linked to more than one entity, and a new linkable entity type doesn't
need a schema change. `app/document_service.py` is the single place that
creates, fetches, and unlinks/deletes documents through that table.

`vendors` (contact details, a type) have a `service_records` history —
each visit optionally links to one `appliance` (some vendor work, like a
roof repair, isn't about any single appliance) but always carries its own
`household_id` for scoping. Logging a visit from an appliance's page can
pick an existing vendor or quick-create one inline
(`app/vendor_service.py`); logging one from a vendor's own page skips that
step since the vendor is already known.

`paint_colors` is a household-scoped, standalone list (one row per
color+location pair — the same color used in two rooms is just entered
twice) with a `hex_color` validated server-side (`app/routes/helpers.parse_hex_color`)
against `#RRGGBB` before it's ever rendered as a CSS swatch.
