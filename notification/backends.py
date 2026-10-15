import sys
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

class OneLineConsoleBackend(BaseEmailBackend):
    """Local dev: print one line per email instead of the whole message."""

    def send_messages(self, email_messages):
        for message in email_messages:
            sys.stdout.write(f"[email] to={', '.join(message.to)} | {message.subject}\n")
        sys.stdout.flush()
        return len(email_messages)


class EnvironmentTaggedSMTPBackend(SMTPEmailBackend):
    """Real SMTP; on UAT every subject starts with [UAT]."""

    def send_messages(self, email_messages):
        tag = settings.EMAIL_SUBJECT_TAG
        if tag:
            for message in email_messages:
                if not message.subject.startswith(tag):
                    message.subject = f"{tag} {message.subject}"
        return super().send_messages(email_messages)