from django.views.generic import TemplateView

from domain.portal.views.base import PortalMixin


class MatchesView(PortalMixin, TemplateView):
    """
    My Matches. Shortlisting is built in the matching phase; until then this shows
    the empty state from the approved design.
    """
    # TODO (matching): list the member's shortlist entries with redacted cards and
    # Interested / Not for me. Mutual interest rules still to confirm with Elyria (Open Questions #11).
    template_name = "domain/portal/matches/matches.html"
    portal_nav = "matches"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["matches"] = []
        return context