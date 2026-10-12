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
Bootstrap 5 (no JS build step), served by uvicorn (via `a2wsgi`, beside the
remote MCP endpoint). Modeled on the `ledger_finance`
app's structure and deployment approach.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env   # SECRET_KEY + the Google sign-in settings below

FLASK_APP=run.py .venv/bin/flask db upgrade
FLASK_APP=run.py .venv/bin/flask seed-templates

.venv/bin/python run.py   # http://localhost:5100 (site only; Flask dev server)
.venv/bin/uvicorn asgi:app --port 5100 --reload   # site + remote MCP at /mcp
```

## Sign-in (Google, allowlist only)

Every request — pages, uploads, static files, even unknown URLs — requires a
signed-in Google account whose email is on the server's allowlist. The only
exceptions are the login page, the Google OAuth endpoints, and the three
static files the login page itself loads. There are no passwords and no
self-serve sign-up.

1. In Google Cloud Console, create an OAuth client of type **Web application**.
   Add `https://<your-domain>/auth/google/callback` (and, for local dev,
   `http://localhost:5100/auth/google/callback`) as authorized redirect URIs.
   Google only accepts `https` + a domain name, or `localhost`, so a LAN IP
   won't work — use a real domain or e.g. a Tailscale `*.ts.net` HTTPS name.
   Leaving the consent screen in **Testing** mode with the same accounts as
   test users gives you a second, Google-side allowlist.
2. Set in `.env`:
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI` — the exact callback URL registered above
     (required in production, where TLS ends at the proxy)
   - `HOMEBASE_ALLOWED_EMAILS` — comma-separated Google accounts, e.g.
     `alice@gmail.com,bob@gmail.com`. Matching ignores case and, for Gmail,
     the dots Google itself ignores.
3. Restart. With `FLASK_ENV=production` the app refuses to start if any of
   these is missing; in development it starts but nobody can sign in.

The allowlist exists only in server config — there is no admin UI or table
for it. The first allowed sign-in creates that user (and the household, on a
fresh install); everyone on the list shares the one household. To revoke
access, remove the address and restart: the allowlist is re-checked on every
request, so an existing session stops working immediately. Sessions last 14
days; rotating `SECRET_KEY` signs everyone out.

If nginx serves `/static` directly, it bypasses this check — let Flask serve
it (the Docker setup does) or protect that location in nginx too.

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
  service_record_service.py   # Creates a ServiceRecord for an appliance or zone
  context_export_service.py   # Builds the Markdown context export
  feature_request_data.py     # Agent feature request choices, fields, instructions
  feature_request_service.py  # Validates/reviews/renders agent feature requests
  auth_service.py             # Google sign-in: allowlist matching + user provisioning
  access_control.py           # Deny-by-default guard run before every request
  cli.py                      # `flask seed-templates`, `flask mcp-token`
  mcp_server.py               # MCP tools: log service visits, file feature requests
  mcp_http.py                 # One ASGI app: /mcp (bearer token) + the Flask site
  mcp_token_service.py        # Remote MCP bearer tokens (config-only, hashed)
asgi.py                         # Production entry point (uvicorn asgi:app)
  routes/                     # Blueprint, split by domain
  templates/, static/         # Jinja2 templates, Bootstrap-based
migrations/                    # Alembic migrations
tests/                          # pytest suite (in-memory SQLite per test)
docs/appliance-tracker-plan.md  # Architecture & build plan
```

## CLI commands

- `flask seed-templates` — (re)loads `category_templates` from
  `app/category_templates_data.py`; safe to re-run, it replaces existing rows
- `flask mcp-token <name>` — generates a remote MCP bearer token and prints the
  `HOMEBASE_MCP_TOKENS` entry for it (see Remote MCP below); stores nothing

## MCP server

`app/mcp_server.py` defines a basic [MCP](https://modelcontextprotocol.io)
server so an LLM client can log service visits for you. Run it locally over
stdio (e.g. for Claude Desktop):

```bash
.venv/bin/python -m app.mcp_server
```

or reach it remotely over HTTPS (see Remote MCP below).

It exposes `list_appliances`, `list_zones`, and `list_vendors` (read-only
lookups) and `create_service` (logs a vendor visit against an existing
appliance or zone, reusing a vendor by name or creating a stub for a new
one). It never creates appliances, zones, or rooms — those stay a manual
step in the web app. It operates on the single household this instance was
set up for, so sign in to the web app once first so the household exists.

It also exposes feature-request tools (see below): `feature_request_instructions`,
`list_feature_requests`, `get_feature_request`, `submit_feature_request`, and
`update_feature_request`. There's deliberately no tool to approve or deny.

### Remote MCP (for hosted AI agents)

The same tools are served at `https://<your-domain>/mcp` (streamable HTTP,
stateless, JSON responses) for agents that can't run a local process. Every
request needs `Authorization: Bearer <token>`; tokens unlock only these tools,
never the website, which still requires Google sign-in.

Tokens are configured only in server env, like the email allowlist:

1. `flask mcp-token muse` prints a new token (give it to the agent; it isn't
   stored anywhere) and a `muse:<sha256>` entry.
2. Add the entry to `HOMEBASE_MCP_TOKENS` (comma-separate one per agent) and
   restart. A malformed entry stops startup rather than being ignored.
3. To revoke, remove the entry and restart. Each request is logged with the
   agent's name (`MCP request from muse`); rejected tokens log a warning.

This needs the ASGI server: `entrypoint.sh` runs `uvicorn asgi:app`. Running
`gunicorn run:app` still serves the site but not `/mcp`. Clients that only
support OAuth-based MCP auth (not a static bearer token) can't connect.

## Agent feature requests

`/agent-request` is an unlisted page (no nav link, `noindex`) where AI agents
using the site file feature requests when they notice something missing. The
homeowner reviews each one (Unread → Approved / Denied → Implemented) and can
edit it. Instructions for agents are shown on the page itself (and returned by
the `feature_request_instructions` MCP tool). Each request is also available as
Markdown at `/agent-request/<id>.md` for a follow-on agent to build from.
Agents filing through the MCP tools can't approve their own requests (there's
no tool for it); an agent driving a browser signed in as you could, and the
instructions tell it not to.

## Deployment

### Docker Compose

```bash
cp .env.example .env   # set SECRET_KEY + Google sign-in settings (see Sign-in)
docker compose up --build -d
```

The app listens on port 5100, with `./data` (SQLite DB + uploaded files) and
`./logs` bind-mounted so they persist across container rebuilds. Run
`docker compose exec homebase flask seed-templates` once the container is up,
then sign in with an allowlisted Google account.

### Raspberry Pi (self-hosted, alongside `ledger_finance`)

Same shape as `ledger_finance`'s deployment: either the Docker Compose setup
above, or Nginx (reverse proxy + TLS — required, since Google sign-in needs https)
in front of uvicorn (`uvicorn asgi:app`) managed by a systemd unit, running on
a different port than `ledger_finance`. `entrypoint.sh` runs `flask db upgrade`
automatically before starting uvicorn, so deploys are just "pull, rebuild, restart."

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
