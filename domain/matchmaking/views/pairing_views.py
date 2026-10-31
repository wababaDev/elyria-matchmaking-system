from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms.pairing_forms import (
    ApprovalForm,
    ClosePairingForm,
    FindMatchForm,
    IntroductionForm,
    PresentForm,
    ProposePairingForm,
)
from domain.matchmaking.models import Client, MatchAccessLog
from domain.matchmaking.models.pairing import OPEN_PAIRING_LIMIT
from domain.matchmaking.services.blurred_photo import blurred_jpeg
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.member_service import members_visible_to
from domain.matchmaking.services.pairing_service import (
    answer_approval,
    can_manage,
    candidates_for,
    close_pairing,
    log_access,
    open_pairing_counts,
    pairings_visible_to,
    present_to_b,
    propose,
    record_introduction,
)

PER_PAGE = 20


def member_page(client):
    return reverse("matchmaking:member-detail", args=[client.pk]) + "#pairings"


class FindMatchView(StaffRequiredMixin, TemplateView):
    """Candidates for one of your own members. Other matchmakers' members appear as a short card only."""
    permission_required = "base.manage_matching"
    template_name = "domain/management/pairings/find_match.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        member = get_object_or_404(
            members_visible_to(self.request.user).select_related("profile"), pk=self.kwargs["pk"]
        )
        profile = getattr(member, "profile", None)

        # Start from the member's own preferred age range
        initial = {"age_min": getattr(profile, "partner_age_min", None), "age_max": getattr(profile, "partner_age_max", None)}
        form = FindMatchForm(self.request.GET or None, initial=initial)
        filters = form.cleaned_data if form.is_bound and form.is_valid() else initial

        candidates = candidates_for(member, **{k: v for k, v in filters.items() if v not in (None, "")})
        page = Paginator(candidates, PER_PAGE).get_page(self.request.GET.get("page"))
        counts = open_pairing_counts(page.object_list)
        mine = set(members_visible_to(self.request.user).values_list("pk", flat=True))

        log_access(self.request.user, MatchAccessLog.Action.SEARCH, member,
                   f"page {page.number}; " + ", ".join(f"{k}={v}" for k, v in filters.items() if v))

        params = self.request.GET.copy()
        params.pop("page", None)
        context.update(
            member=member,
            profile=profile,
            profile_ready=bool(profile and profile.is_complete),
            form=form,
            page_obj=page,
            cards=[
                {"client": c, "profile": c.profile, "open_pairings": counts.get(c.pk, 0),
                 "mine": c.pk in mine, "at_limit": counts.get(c.pk, 0) >= OPEN_PAIRING_LIMIT}
                for c in page.object_list
            ],
            member_open_pairings=open_pairing_counts([member])[member.pk],
            limit=OPEN_PAIRING_LIMIT,
            propose_form=ProposePairingForm(),
            filter_query=params.urlencode(),
        )
        return context


class ProposePairingView(StaffRequiredMixin, View):
    permission_required = "base.manage_matching"
    http_method_names = ["post"]

    def post(self, request, pk):
        member = get_object_or_404(members_visible_to(request.user), pk=pk)
        form = ProposePairingForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Write the note your member will read.")
            return redirect("matchmaking:find-match", member.pk)
        candidate = get_object_or_404(Client, pk=form.cleaned_data["candidate"])
        try:
            pairing = propose(
                member, candidate, by=request.user,
                note_for_a=form.cleaned_data["note"],
                b_profession=form.cleaned_data["profession"],
                b_location=form.cleaned_data["location"],
            )
        except InvalidTransitionError as e:
            messages.error(request, str(e))
            return redirect("matchmaking:find-match", member.pk)

        if pairing.approval == pairing.Approval.PENDING:
            messages.success(request, "Pairing proposed. It's waiting for the other matchmaker's approval.")
        else:
            messages.success(request, f"Pairing proposed. {member.preferred_name} can now see it in their portal.")
        return redirect(member_page(member))


class PairingActionView(StaffRequiredMixin, View):
    """Base for actions on an existing pairing. You must manage at least one of the two members."""
    permission_required = "base.manage_matching"
    http_method_names = ["post"]
    form_class = None

    def perform(self, pairing, data):
        raise NotImplementedError

    def back_to(self, pairing):
        """Your own member's page."""
        mine = pairing.client_a if can_manage(self.request.user, pairing.client_a) else pairing.client_b
        return member_page(mine)

    def post(self, request, pk):
        pairing = get_object_or_404(pairings_visible_to(request.user), pk=pk)
        form = self.form_class(request.POST)
        if not form.is_valid():
            messages.error(request, "Please fill in the required details.")
        else:
            try:
                message = self.perform(pairing, form.cleaned_data)
                messages.success(request, message)
            except InvalidTransitionError as e:
                messages.error(request, str(e))
        return redirect(self.back_to(pairing))


class ApprovePairingView(PairingActionView):
    form_class = ApprovalForm

    def back_to(self, pairing):
        return member_page(pairing.client_b)

    def perform(self, pairing, data):
        approve = data["approve"] == "yes"
        answer_approval(pairing, by=self.request.user, approve=approve, reason=data["reason"])
        return "Approved. The other member can now see the card." if approve else "Declined. Nobody was shown anything."


class PresentPairingView(PairingActionView):
    form_class = PresentForm

    def back_to(self, pairing):
        return member_page(pairing.client_b)

    def perform(self, pairing, data):
        present_to_b(pairing, by=self.request.user, note_for_b=data["note"],
                     a_profession=data["profession"], a_location=data["location"])
        return "Presented. Your member can now see the card in their portal."


class IntroductionPairingView(PairingActionView):
    form_class = IntroductionForm

    def perform(self, pairing, data):
        record_introduction(pairing, by=self.request.user, introduced_on=data["introduced_on"])
        return "Introduction date recorded."


class ClosePairingView(PairingActionView):
    form_class = ClosePairingForm

    def perform(self, pairing, data):
        close_pairing(pairing, by=self.request.user, reason=data["reason"])
        return "Pairing closed. It stays on record."


class CandidatePhotoView(StaffRequiredMixin, View):
    """Blurred photo for match cards: the only photo staff see of other matchmakers' members."""
    permission_required = "base.manage_matching"

    def get(self, request, client_pk):
        client = get_object_or_404(Client.objects.select_related("profile"), pk=client_pk)
        data = blurred_jpeg(client)
        if data is None:
            raise Http404
        response = HttpResponse(data, content_type="image/jpeg")
        response["Cache-Control"] = "private, max-age=600"
        return response


class PairingListView(StaffRequiredMixin, TemplateView):
    """Every pairing involving your members, wherever it's waiting (Admin: all)."""
    permission_required = "base.manage_matching"
    template_name = "domain/management/pairings/list.html"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        from domain.matchmaking.services.pairing_service import OVERVIEW_FILTERS, pairing_overview

        context = super().get_context_data(**kwargs)
        show = self.request.GET.get("show")
        if show not in dict(OVERVIEW_FILTERS):
            # Open on "Waiting on me" when something needs you, otherwise on all open pairings
            show = "me" if pairing_overview(self.request.user, "me") else "open"
        rows = pairing_overview(self.request.user, show)
        page = Paginator(rows, self.paginate_by).get_page(self.request.GET.get("page"))
        context.update(filters=OVERVIEW_FILTERS, show=show, rows=page.object_list, page_obj=page)
        return context