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
from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.services.consultation_request_service import (
    LIST_FILTERS,
    InvalidTransitionError,
    assign_request,
    decline_request,
    filter_consultation_requests,
    mark_fee_paid,
)
from domain.matchmaking.services.consultation_service import (
    book_consultation,
    mark_consulted,
    save_consultation_notes,
)


class ConsultationRequestListView(StaffRequiredMixin, ListView):
    permission_required = "base.view_consultation_request"
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
            base_query=urlencode({k: v for k, v in {"q": q, "assigned": assigned}.items() if v}),
        )
        return context


class ConsultationRequestDetailView(StaffRequiredMixin, DetailView):
    permission_required = "base.view_consultation_request"
    model = ConsultationRequest
    template_name = "domain/management/consultation_requests/detail.html"
    context_object_name = "consultation_request"

    def get_queryset(self):
        return ConsultationRequest.objects.select_related(
            "assigned_to", "fee_marked_paid_by", "consultation", "consultation__conducted_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        consultation = getattr(self.object, "consultation", None)
        context.update(
            consultation=consultation,
            fee_form=FeePaymentForm(),
            book_form=BookConsultationForm(
                initial={"scheduled_for": consultation.scheduled_for} if consultation else None
            ),
            notes_form=ConsultationNotesForm(initial={"notes": consultation.notes if consultation else ""}),
            assign_form=AssignForm(initial={"assigned_to": self.object.assigned_to_id}),
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
            messages.success(request, self.success_message.format(name=consultation_request.preferred_name))
        return self._back(consultation_request)

    def _back(self, consultation_request):
        return redirect("matchmaking:consultation-request-detail", pk=consultation_request.pk)


class MarkFeePaidView(ConsultationRequestActionView):
    form_class = FeePaymentForm
    success_message = "Consultation fee marked as paid for {name}."

    def perform(self, consultation_request, data):
        mark_fee_paid(
            consultation_request,
            by=self.request.user,
            amount=data["amount"],
            currency=data["currency"],
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
        self.success_message = f"Assigned to {user.full_name}." if user else "Request is now unassigned."


class DeclineRequestView(ConsultationRequestActionView):
    success_message = "{name}'s request has been declined."

    def perform(self, consultation_request, data):
        decline_request(consultation_request, by=self.request.user)


class BookConsultationView(ConsultationRequestActionView):
    form_class = BookConsultationForm
    success_message = "Consultation booked for {name}."

    def perform(self, consultation_request, data):
        book_consultation(consultation_request, scheduled_for=data["scheduled_for"], by=self.request.user)


class SaveNotesView(ConsultationRequestActionView):
    form_class = ConsultationNotesForm
    success_message = "Notes saved."

    def perform(self, consultation_request, data):
        save_consultation_notes(consultation_request, notes=data["notes"], by=self.request.user)


class MarkConsultedView(ConsultationRequestActionView):
    """Saves the notes in the box, then marks the consultation as held."""
    form_class = ConsultationNotesForm
    success_message = "{name}'s consultation is marked as held."

    def perform(self, consultation_request, data):
        save_consultation_notes(consultation_request, notes=data["notes"], by=self.request.user)
        mark_consulted(consultation_request, by=self.request.user)