from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.detail import SingleObjectMixin

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.services.consultation_request_service import (
    LIST_FILTERS,
    InvalidTransitionError,
    assign_request,
    decline_request,
    filter_consultation_requests,
    mark_fee_paid,
)


class ConsultationRequestListView(StaffRequiredMixin, ListView):
    permission_required = "base.view_consultation_request"
    template_name = "domain/management/consultation_requests/list.html"
    context_object_name = "consultation_requests"
    paginate_by = 20

    def get_queryset(self):
        return filter_consultation_requests(
            status=self.request.GET.get("status", "open"),
            query=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = LIST_FILTERS
        context["current_status"] = self.request.GET.get("status", "open")
        context["q"] = self.request.GET.get("q", "")
        return context


class ConsultationRequestDetailView(StaffRequiredMixin, DetailView):
    permission_required = "base.view_consultation_request"
    model = ConsultationRequest
    template_name = "domain/management/consultation_requests/detail.html"
    context_object_name = "consultation"

    def get_queryset(self):
        return ConsultationRequest.objects.select_related("assigned_to", "fee_marked_paid_by")


class ConsultationRequestActionView(StaffRequiredMixin, SingleObjectMixin, View):
    """Base for the POST-only buttons on the detail page."""
    permission_required = "base.manage_consultation_request"
    model = ConsultationRequest
    http_method_names = ["post"]
    success_message = ""

    def perform(self, consultation):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        consultation = self.get_object()
        try:
            self.perform(consultation)
        except InvalidTransitionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, self.success_message.format(name=consultation.preferred_name))
        return redirect("matchmaking:consultation-request-detail", pk=consultation.pk)


class MarkFeePaidView(ConsultationRequestActionView):
    success_message = "Consultation fee marked as paid for {name}."

    def perform(self, consultation):
        mark_fee_paid(consultation, by=self.request.user)


class AssignToMeView(ConsultationRequestActionView):
    success_message = "{name}'s request is now assigned to you."

    def perform(self, consultation):
        assign_request(consultation, to=self.request.user)


class DeclineRequestView(ConsultationRequestActionView):
    success_message = "{name}'s request has been declined."

    def perform(self, consultation):
        decline_request(consultation, by=self.request.user)