from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from domain.matchmaking.models import Client, Pairing
from domain.matchmaking.services.blurred_photo import blurred_jpeg
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.pairing_service import member_can_see_photo, member_card, member_decides, member_pairings
from domain.portal.views.base import PortalMixin


class MatchesView(PortalMixin, TemplateView):
    """My Matches: only introductions a matchmaker has presented to this member."""
    template_name = "domain/portal/matches/matches.html"
    portal_nav = "matches"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["matches"] = [member_card(p, self.client) for p in member_pairings(self.client)]
        return context


class MatchDecisionView(PortalMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        pairing = get_object_or_404(Pairing, pk=pk)
        interested = request.POST.get("decision") == "interested"
        try:
            member_decides(pairing, self.client, interested=interested)
        except InvalidTransitionError as e:
            messages.error(request, str(e))
            return redirect("portal:matches")
        if interested:
            messages.success(request, "Thank you. Your matchmaker will be in touch about next steps.")
        else:
            messages.success(request, "Thank you for letting us know. This introduction has been removed.")
        return redirect("portal:matches")


class MatchPhotoView(PortalMixin, View):
    """The blurred photo of someone presented to this member, and nobody else's."""

    def get(self, request, client_pk):
        if not member_can_see_photo(self.client, client_pk):
            raise Http404
        data = blurred_jpeg(get_object_or_404(Client.objects.select_related("profile"), pk=client_pk))
        if data is None:
            raise Http404
        response = HttpResponse(data, content_type="image/jpeg")
        response["Cache-Control"] = "private, max-age=600"
        return response