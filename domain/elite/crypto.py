"""
Encryption for the named person's details, and keyed hashes for the "do not approach" register.

Key: settings.ELITE_ENCRYPTION_KEY (a Fernet key; generate one with
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
). If it isn't set, a key is derived from SECRET_KEY, which is fine for local work, but on UAT and
production set ELITE_ENCRYPTION_KEY so that rotating SECRET_KEY never makes these details unreadable.
"""
import base64
import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _key():
    configured = getattr(settings, "ELITE_ENCRYPTION_KEY", "")
    if configured:
        return configured.encode()
    return base64.urlsafe_b64encode(hashlib.sha256(f"elite:{settings.SECRET_KEY}".encode()).digest())


def encrypt(text):
    if not text:
        return ""
    return Fernet(_key()).encrypt(text.encode()).decode()


def decrypt(token):
    if not token:
        return ""
    try:
        return Fernet(_key()).decrypt(token.encode()).decode()
    except InvalidToken:
        return "[unreadable: encryption key changed]"


def normalise_name(name):
    return " ".join(name.lower().split())


def normalise_contact(contact):
    """Emails are compared lower-case; phone numbers by their digits (last 9, so +260 / 0 prefixes match)."""
    contact = contact.strip().lower()
    if "@" in contact:
        return contact
    digits = re.sub(r"\D", "", contact)
    return digits[-9:] if len(digits) >= 9 else digits


def fingerprint(value):
    """A keyed hash: can be matched against later, but can't be turned back into the name or contact."""
    if not value:
        return ""
    return hmac.new(_key(), value.encode(), hashlib.sha256).hexdigest()