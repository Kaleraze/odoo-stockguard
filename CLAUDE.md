# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

StockGuard is a custom Odoo 17 Community Edition module for specialized warehouse
management: lot/serial tracking plus a multi-level approval workflow. It's the first
of a 3-project portfolio built to show ERP Developer / ERP Technical Consultant skills
for the Thai market. The other two projects — Legacy2Odoo (an idempotent ETL pipeline
+ webhook receiver into Odoo) and ERP Copilot (an MCP-based RAG agent over Odoo, reusing
an existing FastAPI + Qdrant + Ollama RAG agent) — are future work and out of scope
until this one is finished.

The developer is a new ICT graduate (May 2026) moving into ERP work, coming from a
Python / FastAPI / Docker / PostgreSQL background, and is learning Odoo's framework
(ORM, decorators, manifests, views, QWeb) for the first time on this project.

## Constraints

- Open-source tooling only: Odoo Community Edition, self-hosted. No paid/hosted
  automation platforms (n8n, Zapier, etc.) anywhere in this stack.

## Tech stack

Odoo 17 Community, Docker + Docker Compose, PostgreSQL, Python 3.10+, XML (views),
QWeb (PDF reports).

## Working with this repo

- Teach as you go: explain each new piece (Odoo concepts like ORM/decorators/
  manifests, config files like `docker-compose.yml`/`odoo.conf`, and error
  tracebacks when debugging) briefly and in context, right where it shows up —
  not as standalone lectures, and not skipped because a step "looks obvious."
- **Explain it the way you'd brief a client, not a core developer.** The user
  asked for this explicitly after Phase 2. Lead with what the thing does in plain
  business terms, then name the Odoo term for it — never the reverse. Warm and
  conversational, short sentences, concrete warehouse examples over abstract
  framework vocabulary. The technical names still matter (they're needed on the
  job), but they should land as "oh, that's what it's called" rather than as the
  price of admission to the sentence.
- Follow real Odoo coding/module conventions, not just code that happens to run.
- Write tests (Odoo `TransactionCase`) alongside each phase's business logic, not
  bolted on afterward.
- Before moving to the next phase, summarize what skills the finished phase
  demonstrates — this feeds the project's README at the end.

## Phase plan (this project: StockGuard)

- [x] Phase 0: Dev environment — `docker-compose.yml` running Odoo + PostgreSQL
- [x] Phase 1: "Hello World" module (`addons/stockguard`) to get familiar with the
      module workflow — model `stockguard.hello`, access rights, tree/form views,
      2 passing `TransactionCase` tests
- [x] Phase 2: Data model — `stock.lot` extended via `_inherit` (not a parallel
      `stock.lot.custom` model, which would have orphaned the data from real
      inventory), plus new models `warehouse.approval.request` (header) and
      `warehouse.approval.line` (per-level approvals). Sequence, 3 security
      groups, record rule, 12 passing tests.
- [x] Phase 3: Core business logic — computed progress fields (`current_level`,
      `pending_approver_ids`, `can_approve`), Python + SQL constraints, and the
      `draft → pending_approval → approved/rejected` state machine with
      level-by-level approval, plus the side effect that an approved quarantine
      release clears `lot_id.is_restricted`. 34 tests green.
- [x] Phase 4: Views — tree/form/kanban/search/graph/pivot for the approval
      request (buttons driven by `can_approve`, chatter, editable line tree),
      plus inherited `stock.lot` form/tree carrying the StockGuard fields and an
      "Approvals" smart button. Menus live in `views/stockguard_menus.xml`; the
      Hello World menu is now behind `base.group_no_one` (developer mode only).
      `pending_approver_ids` gained a `search=` method so the "Waiting For Me"
      filter works on a non-stored computed field. 43 tests green.
- [x] Phase 5: QWeb PDF report — `report/` holds the template and the
      `ir.actions.report` record, bound to the model so it shows up in the form's
      Print menu. Prints several requests at once, one page each, with a coloured
      status stamp. 51 tests green.
- [ ] Phase 6: Deploy + README/architecture diagram

Current status: Phase 5 done, 51 tests green. Next up is Phase 6 (deploy + README
+ architecture diagram), which also includes deleting the `stockguard.hello`
scaffolding from Phase 1 and its developer-mode menu.

Sample data seeded in the dev database: six approval requests covering every
state (`WAR/2026/00216` is waiting on Mitchell Admin, so the Approve button is
clickable straight after logging in as `admin`), and two approver logins
`somchai` / `somying` (password same as login, both in Warehouse Approver +
Stock User groups) for walking the workflow as different people in the UI.

### Two PDF gotchas found in Phase 5

**Never force real PDF rendering inside a test run.** Odoo falls back to HTML on
purpose when `test_enable` is set; `force_report_rendering=True` makes it spawn
wkhtmltopdf, which fetches the stylesheets back over HTTP from the Odoo server —
and the test recipe stops the web container first, so it hangs until timeout
(this ate a 10-minute run). Test the HTML output instead; verify the real PDF by
rendering through `odoo shell` while the web container is up.

**Background colours do not print.** A Bootstrap `badge text-bg-success` stamp
rendered as white text on white paper because wkhtmltopdf drops background fills
by default. Use coloured text plus a border for anything that must be visible on
the printed page.

### Odoo gotcha worth remembering (found by a test in Phase 3)

A non-stored computed field whose result depends on *who is asking* must carry
`@api.depends_context('uid')`. Without it Odoo caches one value for the whole
transaction and hands the first user's answer to everyone else — `can_approve`
returned True for the level-2 approver while level 1 was still pending.

### Known gotchas

**Never run a CLI install/update while the web container is up.** Two Odoo
processes writing `ir_module_module` at once gives
`psycopg2.errors.SerializationFailure: could not serialize access due to
concurrent update`, and the failure is *not* cleanly atomic — Odoo commits
between module-loading steps, so the module state rolls back while data it
already wrote stays behind, leaving the database inconsistent. Always
`docker compose stop odoo` first and use `docker compose run --rm` (see Commands).

**Always scope `--test-enable` with `--test-tags /stockguard`.** Without it, a
run that installs a new dependency also runs *that* module's entire test suite,
and Odoo core tests commit their fixtures to the database — Phase 2 ended up with
a stray `CHIC1` warehouse and 4 junk `stock.lot` rows this way.

**The web server caches its model registry at startup.** After any CLI
install/update it won't know about new models until restarted — it throws
`KeyError: '<model.name>'` on requests touching them. The Commands recipe below
already ends with a restart.

## Commands

- `docker compose up -d` — start Odoo + PostgreSQL (first run pulls images, takes a while)
- `docker compose stop` — pause the stack, keeping containers/data (fast to resume)
- `docker compose down` — stop and remove containers (named volumes/data survive)
- Update a module and run its tests (the only safe recipe — see "Known gotchas"):
  ```
  docker compose stop odoo
  docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf -d stockguard_dev \
    -u stockguard --test-enable --test-tags /stockguard --stop-after-init
  docker compose up -d
  ```
  (On Windows Git Bash, prefix the `run` line with `MSYS_NO_PATHCONV=1` so
  `/etc/odoo/odoo.conf` isn't mangled into a Windows path.)
- Rebuild the dev database from scratch (it holds nothing precious):
  ```
  docker compose stop odoo
  docker compose exec db dropdb -U odoo stockguard_dev
  docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf -d stockguard_dev \
    -i stockguard --test-enable --test-tags /stockguard --stop-after-init
  docker compose up -d
  ```
- Inspect the database directly:
  `docker compose exec db psql -U odoo -d stockguard_dev -c "<SQL>"`
- App at http://localhost:8069 — dev db `stockguard_dev`, login `admin` / `admin`,
  database-manager master password `admin`
