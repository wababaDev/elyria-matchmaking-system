from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.detail import SingleObjectMixin

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms import (
    AssignForm,
    BookConsultationForm,
    ConsultationNotesForm,
    FeePaymentForm,
    staff_members,
)
from domain.matchmaking.forms.staff_forms import ConfirmMembershipForm, ConsultationRequestDetailsForm, UndoFeePaidForm
from domain.matchmaking.services.membership_service import confirm_membership
from django.utils import timezone
from domain.matchmaking.models import ConsultationRequest, MembershipTier
from domain.matchmaking.services.consultation_request_service import (
    LIST_FILTERS,
    InvalidTransitionError,
    assign_request,
    decline_request,
    filter_consultation_requests,
    mark_fee_paid,
    requests_visible_to,
    undo_fee_paid,
    update_request_details,
)
from domain.matchmaking.services.consultation_service import (
    book_consultation,
    mark_consulted,
    save_consultation_notes,
)
from domain.website.models import SiteSettings
from django.utils.decorators import method_decorator  # not needed, ignore if your linter complains
from django.views.generic import UpdateView
from notification.services.consultation_emails import resend_payment_instructions

class ConsultationRequestListView(StaffRequiredMixin, ListView):
    permission_required = "base.view_all_consultation_requests"
    template_name = "domain/management/consultation_requests/list.html"
    context_object_name = "consultation_requests"
    paginate_by = 20

    def _assigned_param(self):
        assigned = self.request.GET.get("assigned", "")
        return str(self.request.user.pk) if assigned == "me" else assigned

    def get_queryset(self):
        return filter_consultation_requests(
            status=self.request.GET.get("status", "open"),
            query=self.request.GET.get("q", ""),
            assigned=self._assigned_param(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "")
        assigned = self.request.GET.get("assigned", "")
        context.update(
            filters=LIST_FILTERS,
            current_status=self.request.GET.get("status", "open"),
            q=q,
            assigned=assigned,
            staff_members=staff_members(),
            # keeps search + assigned filter when switching tabs or pages
            base_query=urlencode(
                {k: v for k, v in {"q": q, "assigned": assigned}.items() if v}
            ),
        )
        return context


class ConsultationRequestDetailView(StaffRequiredMixin, DetailView):
    permission_required = "base.view_consultation_request"
    model = ConsultationRequest
    template_name = "domain/management/consultation_requests/detail.html"
    context_object_name = "consultation_request"

    def get_queryset(self):
        return requests_visible_to(self.request.user).select_related(
            "assigned_to",
            "fee_marked_paid_by",
            "consultation",
            "consultation__conducted_by",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        consultation = getattr(self.object, "consultation", None)
        context.update(
            consultation=consultation,
            fee_form=FeePaymentForm(),
            book_form=BookConsultationForm(
                initial={
                    "scheduled_for": (
                        consultation.scheduled_for if consultation else None
                    ),
                    "location": (
                        consultation.location
                        if consultation and consultation.location
                        else SiteSettings.load().default_consultation_location
                    ),
                }
            ),
            notes_form=ConsultationNotesForm(
                initial={"notes": consultation.notes if consultation else ""}
            ),
            assign_form=AssignForm(initial={"assigned_to": self.object.assigned_to_id}),
            undo_form=UndoFeePaidForm(),
            can_edit_details=self.object.status in ConsultationRequest.OPEN_STATUSES,
            confirm_form=ConfirmMembershipForm(
                initial={
                    "start_date": timezone.localdate(),
                }
            ),
            active_tiers=MembershipTier.objects.filter(is_active=True),
        )

        return context


def _first_error(form):
    field, errors = next(iter(form.errors.items()))
    if field == "__all__":
        return errors[0]
    return f"{field.replace('_', ' ').capitalize()}: {errors[0]}"


class ConsultationRequestActionView(StaffRequiredMixin, SingleObjectMixin, View):
    """Base for the POST-only buttons and small forms on the detail page."""

    permission_required = "base.manage_consultation_request"
    model = ConsultationRequest
    http_method_names = ["post"]
    form_class = None
    success_message = ""

    def get_queryset(self):
        return requests_visible_to(self.request.user)

    def perform(self, consultation_request, data):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        consultation_request = self.get_object()
        data = {}
        if self.form_class is not None:
            form = self.form_class(request.POST)
            if not form.is_valid():
                messages.error(request, _first_error(form))
                return self._back(consultation_request)
            data = form.cleaned_data
        try:
            self.perform(consultation_request, data)
        except InvalidTransitionError as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                self.success_message.format(name=consultation_request.preferred_name),
            )
        return self._back(consultation_request)

    def _back(self, consultation_request):
        return redirect(
            "matchmaking:consultation-request-detail", pk=consultation_request.pk
        )


class MarkFeePaidView(ConsultationRequestActionView):
    form_class = FeePaymentForm
    success_message = "Consultation fee marked as paid for {name}."

    def perform(self, consultation_request, data):
        mark_fee_paid(
            consultation_request,
            by=self.request.user,
        
            
            method=data["method"],
            reference=data["reference"],
        )


class AssignToMeView(ConsultationRequestActionView):
    success_message = "{name}'s request is now assigned to you."

    def perform(self, consultation_request, data):
        assign_request(consultation_request, to=self.request.user)


class AssignRequestView(ConsultationRequestActionView):
    """Admin only: assign to any staff member, or unassign."""

    permission_required = "base.manage_staff"
    form_class = AssignForm

    def perform(self, consultation_request, data):
        user = data["assigned_to"]
        assign_request(consultation_request, to=user)
        self.success_message = (
            f"Assigned to {user.full_name}." if user else "Request is now unassigned."
        )


class DeclineRequestView(ConsultationRequestActionView):
    success_message = "{name}'s request has been declined."

    def perform(self, consultation_request, data):
        decline_request(consultation_request, by=self.request.user)


class BookConsultationView(ConsultationRequestActionView):
    form_class = BookConsultationForm
    success_message = "Consultation booked for {name}."

    def perform(self, consultation_request, data):
        book_consultation(
            consultation_request,
            scheduled_for=data["scheduled_for"],
            location=data["location"],
            by=self.request.user,
        )


class SaveNotesView(ConsultationRequestActionView):
    form_class = ConsultationNotesForm
    success_message = "Notes saved."

    def perform(self, consultation_request, data):
        save_consultation_notes(
            consultation_request, notes=data["notes"], by=self.request.user
        )


class MarkConsultedView(ConsultationRequestActionView):
    """Saves the notes in the box, then marks the consultation as held."""

    form_class = ConsultationNotesForm
    success_message = "{name}'s consultation is marked as held."

    def perform(self, consultation_request, data):
        save_consultation_notes(
            consultation_request, notes=data["notes"], by=self.request.user
        )
        mark_consulted(consultation_request, by=self.request.user)


class ConfirmMembershipView(ConsultationRequestActionView):
    form_class = ConfirmMembershipForm
    success_message = "{name} is now a member. Their sign-in email has been sent."

    def perform(self, consultation_request, data):
        confirm_membership(
            consultation_request,
            tier=data["tier"],
            start_date=data["start_date"],
            
            method=data["method"],
            reference=data["reference"],
            by=self.request.user,
        )


class ConsultationRequestEditView(StaffRequiredMixin, UpdateView):
    """Correct the applicant's submitted details while the request is in progress."""
    permission_required = "base.manage_consultation_request"
    form_class = ConsultationRequestDetailsForm
    template_name = "domain/management/consultation_requests/edit.html"
    context_object_name = "cr"

    def get_queryset(self):
        # Scoped like the detail page, and only open requests can be edited
        return requests_visible_to(self.request.user).filter(status__in=ConsultationRequest.OPEN_STATUSES)

    def form_valid(self, form):
        email_changed = "email" in form.changed_data
        try:
            request_obj = update_request_details(self.object, data=form.cleaned_data, by=self.request.user)
        except InvalidTransitionError as error:
            messages.error(self.request, str(error))
        else:
            message = "Details updated."
            if email_changed and request_obj.status == ConsultationRequest.Status.AWAITING_PAYMENT:
                message += " The email changed: use Resend payment instructions so they receive them."
            messages.success(self.request, message)
        return redirect("matchmaking:consultation-request-detail", pk=self.object.pk)


class ResendPaymentInstructionsView(ConsultationRequestActionView):
    success_message = "Payment instructions sent again to {name}."

    def perform(self, consultation_request, data):
        if consultation_request.status != ConsultationRequest.Status.AWAITING_PAYMENT:
            raise InvalidTransitionError("Payment instructions can only be resent while awaiting payment.")
        resend_payment_instructions(consultation_request)


class UndoFeePaidView(ConsultationRequestActionView):
    # Admin only: reversing a payment record is an owner-level decision
    permission_required = "base.undo_payment"
    form_class = UndoFeePaidForm
    success_message = "Payment undone for {name}. The request is back to awaiting payment."

    def perform(self, consultation_request, data):
        undo_fee_paid(consultation_request, reason=data["reason"], by=self.request.user)