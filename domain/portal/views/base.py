from django.http import Http404
from django.utils.functional import cached_property

from domain.base.mixins import MemberRequiredMixin
from domain.matchmaking.models import Client
from domain.matchmaking.services.profile_service import get_profile


class PortalMixin(MemberRequiredMixin):
    """
    Every portal page. The member's own records always come from request.user,
    never from an ID in the URL, so nobody can open someone else's.
    """
    portal_nav = ""

    @cached_property
    def client(self):
        try:
            return (
                Client.objects.select_related("user", "matchmaker", "consultation_request", "membership__tier")
                .get(user=self.request.user)
            )
        except Client.DoesNotExist:
            raise Http404("No member record for this account.")

    @cached_property
    def profile(self):
        return get_profile(self.client)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(client=self.client, portal_nav=self.portal_nav)
        return context