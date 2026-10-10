from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.detail import SingleObjectMixin

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms import AssignForm, CancelMembershipForm, RenewMembershipForm, staff_members
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.member_service import (
    MEMBER_FILTERS,
    cancel_membership,
    filter_members,
    members_visible_to,
    reassign_matchmaker,
    renew_membership,
)
from domain.matchmaking.views.consultation_request_views import _first_error
from notification.services.member_emails import send_sign_in_link


class MemberListView(StaffRequiredMixin, ListView):
    permission_required = "base.manage_client"
    template_name = "domain/management/members/list.html"
    context_object_name = "members"
    paginate_by = 20

    def get_queryset(self):
        return filter_members(
            members_visible_to(self.request.user),
            status=self.request.GET.get("status", "active"),
            query=self.request.GET.get("q", ""),
            matchmaker=self.request.GET.get("matchmaker", ""),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "")
        matchmaker = self.request.GET.get("matchmaker", "")
        context.update(
            filters=MEMBER_FILTERS,
            current_status=self.request.GET.get("status", "active"),
            q=q,
            matchmaker=matchmaker,
            staff_members=staff_members(),
            base_query=urlencode({k: v for k, v in {"q": q, "matchmaker": matchmaker}.items() if v}),
        )
        return context


class MemberDetailView(StaffRequiredMixin, DetailView):
    permission_required = "base.manage_client"
    template_name = "domain/management/members/detail.html"
    context_object_name = "member"

    def get_queryset(self):
        return members_visible_to(self.request.user).select_related(
            "user", "matchmaker", "consultation_request",
            "consultation_request__consultation", "consultation_request__consultation__conducted_by",
            "membership", "membership__tier",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        membership = getattr(self.object, "membership", None)
        context.update(
            membership=membership,
            payments=membership.payments.select_related("recorded_by") if membership else [],
            consultation=self.object.consultation,
            details=self.object.consultation_request,
            renew_form=RenewMembershipForm(initial={"tier": membership.tier_id if membership else None}),
            cancel_form=CancelMembershipForm(),
            assign_form=AssignForm(initial={"assigned_to": self.object.matchmaker_id}),
        )
        return context


class MemberActionView(StaffRequiredMixin, SingleObjectMixin, View):
    permission_required = "base.manage_client"
    http_method_names = ["post"]
    form_class = None
    success_message = ""

    def get_queryset(self):
        return members_visible_to(self.request.user)

    def perform(self, member, data):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        member = self.get_object()
        data = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                messages.error(request, _first_error(form))
                return redirect("matchmaking:member-detail", pk=member.pk)
            data = form.cleaned_data
        try:
            self.perform(member, data)
        except InvalidTransitionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, self.success_message.format(name=member.preferred_name))
        return redirect("matchmaking:member-detail", pk=member.pk)


class RenewMembershipView(MemberActionView):
    form_class = RenewMembershipForm
    success_message = "{name}'s membership has been renewed."

    def perform(self, member, data):
        renew_membership(member.membership, by=self.request.user, **data)


class CancelMembershipView(MemberActionView):
    form_class = CancelMembershipForm
    success_message = "{name}'s membership has been cancelled and their sign-in disabled."

    def perform(self, member, data):
        cancel_membership(member.membership, reason=data["reason"], by=self.request.user)


class ResendSignInLinkView(MemberActionView):
    success_message = "A new sign-in link has been sent to {name}."

    def perform(self, member, data):
        if not member.user.is_active:
            raise InvalidTransitionError("This member's sign-in is disabled (membership cancelled).")
        send_sign_in_link(member)


class ReassignMatchmakerView(MemberActionView):
    permission_required = "base.manage_staff"
    form_class = AssignForm

    def perform(self, member, data):
        user = data["assigned_to"]
        reassign_matchmaker(member, to=user, by=self.request.user)
        self.success_message = f"Matchmaker changed to {user.full_name}." if user else "Matchmaker removed."