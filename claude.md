# Elyria Matchmaking: project context

Read this first. It is the handover file for any new Claude chat or Claude Code session.
Keep it updated when something important changes (a new app, a new convention, a deployment step).

## What this is

Website, staff backoffice and member portal for **Elyria Matchmaking Limited**, a private
matchmaking service in Lusaka. Built from the client's "Website Content & Design Brief".
One developer, delivered over an ~8-week plan.

- **Public site**: marketing pages, the "Request a Private Consultation" form, the "Learn More" enquiry form per membership tier.
- **Staff backoffice** (`/management/`): consultation requests, consultations, My Queue, members, enquiries, settings.
- **Member portal** (`/portal/`): NOT BUILT YET.

## Stack

- Python 3.11, Django 5.2, Poetry (`package-mode = false`)
- PostgreSQL in production, SQLite locally
- Celery + Redis for all outgoing email
- WhiteNoise for static files (`CompressedStaticFilesStorage`; the manifest version broke the template's CSS)
- Gunicorn in Docker, Caddy on the host
- Frontend: Ombara HTML template (public site), Sash admin template (backoffice). No JS framework.

## Project layout

```
config/
  settings/base.py, local.py, production.py   # no separate uat.py; ENVIRONMENT env var decides
  celery.py
domain/
  base/          # User, Profile, groups/permissions, mixins, auth views, http.client_ip, context processors
  website/       # public pages, SiteSettings (singleton), SiteDocument (privacy PDF)
  matchmaking/   # models, services and STAFF views for the whole pipeline
  portal/        # member-facing views (to be built)
notification/
  services/      # *_emails.py: deliver_* builds/sends one email, notify_*/send_* queues it
  tasks.py       # Celery tasks, take IDs, skip missing records
  backends.py    # OneLineConsoleBackend (local), EnvironmentTaggedSMTPBackend (adds "[UAT]")
docker/
  Dockerfile, entrypoint.sh
docker-compose.yml   # web + worker
.github/workflows/ci.yml
```

## Conventions (follow these)

- `domain/` app per bounded context. Models split into packages (`models/<name>.py`).
- **Business rules live in `services/`**. Views stay thin. Services raise a domain error, views show it as a message.
- **Class-based views only.**
- Notifications are queued with `transaction.on_commit(...)`, never sent inside the request.
- Celery tasks take **IDs**, not objects. `notification/services/queue.py::enqueue()` catches broker errors so a Redis outage never breaks a page.
- Retry policy for email tasks: autoretry on `SMTPException`/`OSError`, backoff from 60s to 1h, 6 retries.
- Shared confirm modal: add `data-confirm="Message"` to a submit button instead of using `confirm()`.

## Roles and permissions (HelpDesk pattern)

Groups: **Member**, **Matchmaker**, **Admin**.
Permissions live on an unmanaged `ElyriaPermissions` model. `create_groups_and_permissions()` /
`manage.py setup_groups` creates them (also run by `entrypoint.sh`).

Mixins: `GroupRequiredMixin`, `StaffRequiredMixin` (login at staff sign-in), `MemberRequiredMixin`, `AdminRequiredMixin`.

**Object scoping:** `requests_visible_to(user)` and `members_visible_to(user)`.
A Matchmaker only sees requests/members **assigned to them** (anything else is a 404).
Admin sees everything and does the assigning.

## The pipeline

1. Applicant submits the consultation form → `ConsultationRequest` created, payment-instructions email to applicant, alert to the team.
   Married/separated applicants are blocked with the brief's message; "Other" status requires an explanation.
2. Admin assigns it to a Matchmaker.
3. Fee marked paid (amount, currency, method, reference). The fee is paid **before** the call-back.
4. Matchmaker books the `Consultation` (date/time + location) → booking email (says "rescheduled" if the time changes).
5. Matchmaker saves notes and marks it consulted (notes required).
6. Confirm membership → creates `Client`, `Membership` (tier FK to `MembershipTier`), `MembershipPayment` (new), a Member user with no password, and a welcome email with a set-password link.
7. Members pages: renew (new payment row, moves end date), cancel, resend link, reassign matchmaker.

Tiers (`MembershipTier`) are configurable in Settings. Bronze, Silver, Gold and Elite Grade are seeded by a migration.
Settings (Admin only): General (`SiteSettings`: fee, payment details, contact, social links), Staff, Tiers, Documents (privacy PDF).
Events page is a static message for now.

## Running locally

```bash
poetry install
poetry run python manage.py migrate
poetry run python manage.py setup_groups
poetry run python manage.py runserver 2004
```

Locally `CELERY_TASK_ALWAYS_EAGER=True` (default), so emails run immediately and print one line each in the terminal. No Redis needed.

## Tests

```bash
poetry run python manage.py test domain notification
poetry run coverage run --source=domain,notification manage.py test domain notification
poetry run coverage report -m --skip-covered
```

Test files live in `domain/<app>/tests/` and `notification/tests/` (each needs `__init__.py`).
In matchmaking tests, requests must be **assigned to the matchmaker** (`self.mine()` helper), or the views 404.
State at last update: 96 tests passing, ~95% coverage. Known gaps: `notification/backends.py`, `setup_groups`, `http.client_ip`.

## Deployment

- Branches: `beta` → UAT, `main` → production. CI runs on push/PR to both: check, `makemigrations --check`, `check --deploy` on production settings, tests, Docker build.
One Hetzner server `elyria-1` (2 vCPU, 4 GB, Ubuntu 26.04, Falkenstein) with Hetzner Backups. Storage Box `elyria-backups` in Helsinki. Accounts (Hetzner, Porkbun domain, Zoho mail) are in the client's name; the developer is a member.
- On the host: PostgreSQL 18 (`elyria_prod`, `elyria_uat`; config in `/etc/postgresql/18/main/`), Redis 8 (password required; db 0 prod, db 1 UAT), Caddy (basic auth on `uat.<domain>`).
- Containers reach the host via `host.docker.internal`. `pg_hba.conf` and ufw only allow 172.16.0.0/12 on 5432/6379; each DB user can only reach its own database.
- SSH: user `wababa` with key only; root login and passwords are off. Hetzner web console works with wababa's password..
- Containers: prod on `127.0.0.1:8000`, UAT on `127.0.0.1:8001`. Folders `/srv/elyria/{prod,uat}`, media `/srv/elyria/media/{prod,uat}`. Each has its own `.env` (see `.env.example`).
- `entrypoint.sh`: migrate → createcachetable → setup_groups → gunicorn.
- Backups: Hetzner Backups + a Storage Box.

## Status and next steps

Done: public site, consultation flow, staff backoffice, settings, members, enquiries, Docker, Celery, CI.

Next:
1. Server setup: non-root user, firewall, SSH hardening, Docker, PostgreSQL, Redis, `/srv` folders and `.env` files, Caddy, first UAT deploy, deploy workflow (deploy user, key, GitHub secrets).
2. Zoho mailboxes and MX records.
3. Member portal (profile), then matching, then renewal reminders (Celery Beat).

Known leftovers: staff header still has `href="dashboard.html"` and sample notifications; public "Member Sign In" link is `#`.

## How the developer likes to work

- Numbered steps.
- Whole files for new or heavily changed files; diffs for small changes.
- No features that weren't asked for. Keep solutions simple.
- Messages often have typos and shorthand. Read for intent, don't point them out.