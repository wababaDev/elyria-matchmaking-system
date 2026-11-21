from django.conf import settings


class NoIndexMiddleware:
    """
    Adds 'X-Robots-Tag: noindex' to every UAT response, and to private areas everywhere
    (back office, portal, Elite). Belt and braces with robots.txt: search engines respect either.
    """

    PRIVATE_PREFIXES = ("/management/", "/portal/", "/elite/", "/sign-in/", "/admin/", "/accounts/")

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_uat = getattr(settings, "ENVIRONMENT", "") == "uat"

    def __call__(self, request):
        response = self.get_response(request)
        if self.is_uat or request.path.startswith(self.PRIVATE_PREFIXES):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response