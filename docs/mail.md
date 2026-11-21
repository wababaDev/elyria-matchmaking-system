# Email: how it works and how to configure it

Everything the system sends (payment instructions, sign-in links, team alerts…) goes out
through **Zoho Mail** over SMTP, from `info@elyriamatchmaking.com`, queued by **Celery** so a
slow or failing mail server never slows down or breaks a page.

---

## 1. How an email travels

```
service (e.g. confirm_membership)
  └─ transaction.on_commit → notify_… / send_…      notification/services/*_emails.py
        └─ enqueue(task, id)                         notification/services/queue.py
              └─ Redis → Celery worker                (locally: runs immediately, no Redis)
                    └─ task loads the record by id    notification/tasks.py
                          └─ deliver_…                builds and sends the email
                                └─ send_templated_email   notification/services/mailer.py
                                      renders <template>.txt + <template>.html
                                      └─ EMAIL_BACKEND → Zoho SMTP
```

- **Tasks take IDs, not objects.** If the record was deleted before the worker ran, the email is skipped and logged.
- **Retries:** network or SMTP errors retry after about 1, 2, 4, 8, 16 and 32 minutes (capped at 1 hour), then give up (`EMAIL_RETRY` in `notification/tasks.py`).
- **`enqueue()` never raises.** If Redis is down, the page still works and the error is logged.

## 2. Every email the system sends

| Email | Sent to | Trigger | Template (`templates/notification/email/`) |
|---|---|---|---|
| Payment instructions | Applicant | Consultation request submitted, or "Resend payment instructions" | `consultation_payment_instructions` |
| New request alert | `TEAM_INBOX_EMAIL` | Consultation request submitted | `consultation_team_alert` |
| Consultation booked / rescheduled | Applicant | Booking saved or changed | `consultation_booked` |
| Enquiry alert | `TEAM_INBOX_EMAIL` | "Learn More" enquiry submitted | `enquiry_team_alert` |
| Welcome + set-password link | New member | Membership confirmed | `member_welcome` |
| Sign-in link | Member | "Resend sign-in link", or email changed before a password was set | `member_sign_in_link` |
| Sign-in email changed | Member (old **and** new address) | Staff change a member's sign-in email | `sign_in_email_changed` |
| Staff invite | New staff member | Staff account created / invite resent | `staff_invite` |
| Profile complete | Assigned matchmaker (or `TEAM_INBOX_EMAIL`) | Member marks profile complete | `profile_completed` |
| Profile updated | Assigned matchmaker (or `TEAM_INBOX_EMAIL`) | Member changes a completed profile | `profile_updated` |

Every template exists twice: **`.txt`** (plain-text fallback, helps spam scores) and **`.html`**
(styled, extends `base.html`: burgundy `#6E1423`, gold `#C9A227`, logo from `SITE_URL`).
**Both files are required**; a missing `.txt` makes the task fail.

Every template also receives `site` (the `SiteSettings` row: contact phone/email etc.) and `site_url`.

## 3. Settings and `.env`

### Settings that read `.env`

| Setting | What it is | Default |
|---|---|---|
| `EMAIL_BACKEND` | How mail is sent (see below) | local: console · server: `notification.backends.EnvironmentTaggedSMTPBackend` |
| `EMAIL_HOST` | SMTP server | `smtppro.zoho.com` |
| `EMAIL_PORT` | SMTP port | `587` |
| `EMAIL_USE_TLS` | STARTTLS on port 587 | `True` |
| `EMAIL_HOST_USER` | The Zoho mailbox that sends | — |
| `EMAIL_HOST_PASSWORD` | **Zoho app password** (not the mailbox password) | — |
| `DEFAULT_FROM_EMAIL` | The "From" shown to people | — |
| `TEAM_INBOX_EMAIL` | Where team alerts go | — |
| `SITE_URL` | Start of every link in emails (no trailing slash) | `http://127.0.0.1:2004` |
| `ENVIRONMENT` | `local` / `uat` / `prod`. On `uat`, subjects get a `[UAT]` tag | `local` |
| `CELERY_BROKER_URL` | Redis for the queue (servers only) | `redis://localhost:6379/0` |
| `CELERY_TASK_ALWAYS_EAGER` | Run tasks immediately, no Redis needed | local: `True` · server: `False` |

### Email backends

| Backend | Use |
|---|---|
| `notification.backends.OneLineConsoleBackend` | Local default: prints one line per email in the terminal |
| `django.core.mail.backends.console.EmailBackend` | Local: prints the **whole** email, including links (handy to copy a set-password link) |
| `notification.backends.EnvironmentTaggedSMTPBackend` | Servers: real SMTP, adds `[UAT]` to subjects when `ENVIRONMENT=uat` |
| `django.core.mail.backends.locmem.EmailBackend` | Tests (Django sets this automatically; emails land in `mail.outbox`) |

### `.env`: local (your laptop)

Nothing is required. Emails print in the `runserver` terminal.

```env
ENVIRONMENT=local
# Print the whole email (to copy links) instead of one line:
# EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

To send **real** email from your laptop (for example, to check how it looks in Gmail), add the Zoho
lines from the server example below and set
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`. Use your own address as the recipient.

### `.env`: UAT (`/srv/elyria/uat/.env`) and production (`/srv/elyria/prod/.env`)

```env
ENVIRONMENT=uat                                  # prod on production
SITE_URL=https://uat.elyriamatchmaking.com       # https://elyriamatchmaking.com on production

EMAIL_BACKEND=notification.backends.EnvironmentTaggedSMTPBackend
EMAIL_HOST=smtppro.zoho.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=info@elyriamatchmaking.com
EMAIL_HOST_PASSWORD=<Zoho app password>
DEFAULT_FROM_EMAIL=Elyria Matchmaking <info@elyriamatchmaking.com>
TEAM_INBOX_EMAIL=enquiries@elyriamatchmaking.com

CELERY_TASK_ALWAYS_EAGER=False
CELERY_BROKER_URL=redis://:<redis password>@host.docker.internal:6379/1   # db 0 = prod, db 1 = UAT
```

- **Never commit `.env`.** Check `git status` before every commit.
- **Never paste passwords into chats, tickets or screenshots.** If one leaks, change it in Zoho straight away and update both `.env` files.
- After changing `.env` on a server: `cd /srv/elyria/uat && docker compose up -d` (the web container and the worker both read it).

## 4. Zoho Mail setup (already done; for reference and handover)

- **Plan:** Zoho Mail Lite, yearly, in Elyria's name. The owner's account is Super Admin.
- **Sending mailbox:** `info@elyriamatchmaking.com`, a real mailbox and an Admin.
- **Aliases** to `info@`: `consultation@`, `bookings@`, `hello@`.
- **Group:** `enquiries@` (team inbox, used as `TEAM_INBOX_EMAIL` and as the contact email in Settings).
- **App password:** Zoho → `info@` account → My Account → Security → App Passwords → create one named "Elyria website". This goes in `EMAIL_HOST_PASSWORD`. It keeps working if the mailbox password changes, and can be revoked on its own.

### DNS records (Porkbun)

| Type | Host | Value |
|---|---|---|
| MX | `@` | Zoho's three MX records (`mx.zoho.com` 10, `mx2.zoho.com` 20, `mx3.zoho.com` 50) |
| TXT | `@` | Zoho domain verification |
| TXT | `@` | SPF: `v=spf1 include:zohomail.com ~all` |
| TXT | `zmail._domainkey` | DKIM key from Zoho (Mail Admin → Domains → Email Configuration → DKIM) |
| TXT | `_dmarc` | `v=DMARC1; p=none;` |

**TODO:** about a month after launch, if reports look clean, change DMARC to `v=DMARC1; p=quarantine;`.

Deliverability check: send an email to the address shown on mail-tester.com (last score: 9.6/10).

## 5. Testing that email works

**Locally**, any action that sends mail prints it in the `runserver` terminal.

**On a server**, inside the web container:
```bash
cd /srv/elyria/uat
sudo docker compose exec web python manage.py sendtestemail you@example.com
```
- Arrives with `[UAT]` in the subject: SMTP settings are right.
- Error `SMTPAuthenticationError`: wrong `EMAIL_HOST_USER` or app password.
- Error about connection or timeout: check `EMAIL_HOST`/`EMAIL_PORT`, and that the server can reach port 587.

`sendtestemail` sends directly, not through Celery. To check the queue too, trigger a real email
(for example "Resend sign-in link" on a test member) and watch the worker:
```bash
sudo docker compose logs -f worker
```

**In tests**, emails go to `mail.outbox`. Code that queues after a commit needs
`with self.captureOnCommitCallbacks(execute=True):`. Set `CELERY_TASK_EAGER_PROPAGATES = True` in local
settings so a broken task (for example a missing template) fails the test instead of silently sending nothing.

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Nothing arrives, no error on the page | Worker not running, or Redis down (the error is in the logs) | `docker compose ps`, `docker compose logs worker` |
| Test says `0 != 1` emails | Missing `.txt`/`.html` template, or the task isn't in `notification/tasks.py` | Check both template files exist and the task is defined |
| "Queued" in Zoho's Sent folder | Normal for a new domain; Zoho releases it shortly | Wait; if it persists, check SPF/DKIM/DMARC |
| Lands in spam | DNS records missing or wrong | Re-check the records above; run mail-tester.com |
| Links in emails point to localhost | `SITE_URL` not set on the server | Set it in `.env`, then `docker compose up -d` |
| Set-password link "expired" | Links last 7 days (`PASSWORD_RESET_TIMEOUT`) and stop working once used or after the email address changes | Staff: "Resend sign-in link" on the member page |

## 7. At handover

1. The owner changes the `info@` mailbox password in Zoho. The app password keeps working.
2. Check it: `sendtestemail` on UAT and production.
3. The owner takes over as Super Admin, and the developer's Zoho account is removed.
4. Optionally, revoke the app password and create a new one, then update both `.env` files.

## 8. Adding a new email

1. Create `templates/notification/email/<name>.html` (extends `base.html`) **and** `<name>.txt`.
2. In the right `notification/services/*_emails.py`, add `deliver_<name>(obj)`, which calls `send_templated_email`, and `notify_<name>(obj)`, which calls `enqueue(tasks.send_<name>_email, obj.pk)`.
3. In `notification/tasks.py`, add `@shared_task(**EMAIL_RETRY) def send_<name>_email(obj_id)`, which loads the record with `_get` and calls `deliver_…`.
4. From the service, call `transaction.on_commit(lambda: notify_<name>(obj))`.
5. Write a test using `captureOnCommitCallbacks(execute=True)` and `mail.outbox`.