from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms.member_note_forms import CloseNoteForm, DiscrepancyForm, NoteEditForm, ObservationForm
from domain.matchmaking.models import MemberNote
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.member_note_service import add_discrepancy, add_observation, close_note, edit_note
from domain.matchmaking.services.member_service import members_visible_to


class MemberNoteActionView(StaffRequiredMixin, View):
    """Base for every Notes action: staff who can manage this member (not Finance), POST only."""
    permission_required = "base.manage_client"
    http_method_names = ["post"]
    form_class = None
    success_message = ""

    def perform(self, member, data):
        raise NotImplementedError

    def post(self, request, pk, note_pk=None):
        member = get_object_or_404(members_visible_to(request.user), pk=pk)
        self.note = get_object_or_404(MemberNote, pk=note_pk, client=member) if note_pk else None
        form = self.form_class(request.POST)
        if not form.is_valid():
            first_error = next(iter(form.errors.values()))[0]
            messages.error(request, first_error)
        else:
            try:
                self.perform(member, form.cleaned_data)
                messages.success(request, self.success_message)
            except InvalidTransitionError as e:
                messages.error(request, str(e))
        return redirect(reverse("matchmaking:member-detail", args=[member.pk]) + "#notes")


class AddObservationView(MemberNoteActionView):
    form_class = ObservationForm
    success_message = "Observation added."

    def perform(self, member, data):
        add_observation(member, category=data["category"], body=data["body"], by=self.request.user)


class AddDiscrepancyView(MemberNoteActionView):
    form_class = DiscrepancyForm
    success_message = "Discrepancy logged."

    def perform(self, member, data):
        add_discrepancy(member, by=self.request.user, **data)


class EditNoteView(MemberNoteActionView):
    form_class = NoteEditForm
    success_message = "Note updated. The earlier version is kept."

    def perform(self, member, data):
        edit_note(self.note, body=data["body"], by=self.request.user)


class CloseNoteView(MemberNoteActionView):
    form_class = CloseNoteForm
    success_message = "Closed."

    def perform(self, member, data):
        close_note(self.note, outcome=data["outcome"], resolution=data["resolution"], by=self.request.user)