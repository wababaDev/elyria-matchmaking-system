# Elyria Matchmaking

The website and private client-management system for **Elyria Matchmaking Limited**, a human-led matchmaking service in Lusaka, Zambia.

It has three parts:

| Part | Who uses it | What it does |
|---|---|---|
| **Public website** | Anyone | Home, About, Services, Membership, Team, Events, FAQ, Privacy. "Request a Private Consultation" and "Apply for Elite Grade" forms. |
| **Member portal** | Members | Self-service profile, photos, My Matches (blurred photos until both say yes). |
| **Back office** | Admin and matchmakers | Consultation requests and records, members and memberships, Find a match, pairings and approvals, introductions and date feedback, payments, Elite Grade cases, dashboard, settings. |

There is no matching algorithm. Matchmakers search and choose; the system enforces the process, the privacy rules and the paperwork.

---

## The client journey (short version)

1. **Enquiry:** the client fills in Request a Private Consultation and gets an automatic email with the consultation fee and payment details.
2. **Consultation:** staff record the fee, book the consultation, and fill in the Official Consultation Record, which is locked once saved.
3. **Membership:** staff confirm the tier and payment. The member gets a login and completes their profile.
4. **Matching:** the matchmaker uses Find a match. A pairing across two matchmakers needs the other matchmaker's approval. Client A decides first, then Client B.
5. **Introduction and feedback:** the date is recorded, and each matchmaker records their own member's feedback, including red flags.
6. **Membership management:** introductions are counted per tier. Members can renew, upgrade or take Hold Time (Silver and Gold, set per tier in Settings).

**Elite Grade** is a separate, private path for one discreet introduction to a named person. It's visible only to Admin and the assigned Case Handler. The named person's details are encrypted, there's a "do not approach" register, and the details are deleted by hand 30 days after the case closes.

---

## Tech stack

- Python 3.11, Django 5.2
- PostgreSQL
- Celery for the email queue, with Celery Beat for daily jobs (reminders, renewals, Elite clean-up)
- Bootstrap-based templates (Ombara theme for the public site)
- Poetry for dependencies
- Hosted on a Hetzner server behind Caddy (HTTPS). Email is sent through Zoho from info@.

---

## Project layout

```
domain/
  base/          users, groups and permissions, shared mixins, middleware
  website/       public pages, site settings, SEO (sitemap, robots.txt)
  matchmaking/   consultation requests and records, members, memberships, tiers,
                 Hold Time, pairings, date feedback, dashboard, settings
  portal/        the member portal
  elite/         Elite Grade cases (encrypted named-person details, "do not approach" register)
notification/    every email: templates (.txt and .html), queue, Celery tasks
templates/       all HTML templates, grouped the same way as domain/
scripts/backup/  the nightly backup script (installed on the server)
```

Each app keeps its logic in `services/`. Views stay thin, and every view is a class-based view. Emails are queued with `enqueue(...)` after the database save commits.

---

## Running it locally

**You need:** Python 3.11, Poetry, PostgreSQL, and Redis (or whatever broker `.env` points Celery at).

1. Install the dependencies:
   ```bash
   poetry install
   ```
2. Create `.env` in the project root. Ask the project owner for the list of settings, and **never commit it**. At minimum it needs:
   - `SECRET_KEY`
   - `DEBUG=True`
   - the database settings
   - `SITE_URL`
   - the email settings (locally, use the console email backend)
   - the Celery broker URL
3. Set up the database:
   ```bash
   poetry run python manage.py migrate
   poetry run python manage.py createsuperuser
   ```
4. (Optional, **local only**) add fake members to test with:
   ```bash
   poetry run python manage.py seed_members
   ```
5. Run the site:
   ```bash
   poetry run python manage.py runserver
   ```
6. In a second terminal, run the worker and the daily jobs:
   ```bash
   poetry run celery -A config worker -B -l info
   ```
   Change `config` if the Django project package has another name.

The back office is at `/management/`, and the member portal at `/portal/`.

---

## Tests

```bash
poetry run python manage.py test                    # everything
poetry run python manage.py test domain.matchmaking  # one app
poetry run python manage.py test domain.elite
```

Run the tests before every push. Messages like "Elite email sent without elite_nda…" are normal in tests, because the test database has no documents uploaded in Settings.

**Migrations:** the Elite app's label is `Elite`, so it's `makemigrations Elite`. For the rest, use `makemigrations matchmaking` (and so on).

---

## Branches and deployment

| Branch | Goes to | Use it for |
|---|---|---|
| `main` | **Production** (the live site) | Only tested work, merged from `beta` |
| `beta` | **UAT**, https://uat.elyriamatchmaking.com | Work for the client to test |
| `ft/<name>` | Nowhere | One feature or fix at a time, e.g. `ft/hold-time` |

Pushing to `beta` or `main` deploys automatically through GitHub Actions. The deploy pulls the code, installs dependencies, runs migrations and `collectstatic`, and restarts the app and the Celery worker.

**The usual flow:**
1. Branch off `beta`: `git checkout -b ft/my-change beta`
2. Build it, write or update tests, and run the tests.
3. Merge into `beta` and push. It deploys to UAT for the client to test.
4. Once the client approves it, merge `beta` into `main` and push. It deploys to production.

Never edit files directly on GitHub or on the server.

---

## Rules that matter

- **Never commit** `.env`, `rclone.conf`, SSH keys or any password.
- **Never change the production `SECRET_KEY`.** The Elite encryption depends on it; change it and the encrypted named-person details can't be read any more.
- **Never run `seed_members` on production.** It's for fake test data only.
- **Use fake data only** for development and testing. Real client data stays on the live system.
- Any change to Elite's encryption, the "do not approach" register or deletion needs extra care. Read `domain/elite/` and its tests first.
- The Elite Grade tier in Settings must keep "Elite" in its name. That's how the Elite fee is found, and how it's kept out of the normal membership forms.

---

## Backups

`scripts/backup/elyria-backup.sh` runs nightly on the server through cron. It:
- dumps the database and archives the uploaded files;
- encrypts them and sends them to a Hetzner Storage Box (kept 14 days);
- on Sundays, also sends a copy to Backblaze B2 (kept 8 weeks).

The script reads `/etc/elyria-backup-<environment>.conf`. The encryption passwords are in the owner's password manager. The restore steps are in the **handover guide**.

---

## More documentation

- **Handover guide:** server, accounts, backups and restore, day-to-day admin
- **Specification and change record:** what the system does, and every approved change
- **UAT test script:** the client's step-by-step tests

These are kept by Elyria. Ask the project owner for access.