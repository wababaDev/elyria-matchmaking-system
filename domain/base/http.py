from django.conf import settings


def client_ip(request):
    """The visitor's address. Behind Caddy, REMOTE_ADDR is Caddy itself."""
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")