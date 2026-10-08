import sys

from django.core.mail.backends.base import BaseEmailBackend


class OneLineConsoleBackend(BaseEmailBackend):
    """Local dev: print one line per email instead of the whole message."""

    def send_messages(self, email_messages):
        for message in email_messages:
            sys.stdout.write(f"[email] to={', '.join(message.to)} | {message.subject}\n")
        sys.stdout.flush()
        return len(email_messages)