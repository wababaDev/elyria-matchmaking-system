from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import DetailView, ListView
from django.views.generic.detail import SingleObjectMixin

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms import AnswerEnquiryForm
from domain.matchmaking.models import Enquiry
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.enquiry_service import ENQUIRY_FILTERS, filter_enquiries, mark_answered


class EnquiryListView(StaffRequiredMixin, ListView):
    permission_required = "base.handle_enquiry"
    template_name = "domain/management/enquiries/list.html"
    context_object_name = "enquiries"
    paginate_by = 20

    def get_queryset(self):
        return filter_enquiries(self.request.GET.get("status", "open"), self.request.GET.get("q", ""))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "")
        context.update(
            filters=ENQUIRY_FILTERS,
            current_status=self.request.GET.get("status", "open"),
            q=q,
            base_query=urlencode({"q": q}) if q else "",
        )
        return context


class EnquiryDetailView(StaffRequiredMixin, DetailView):
    permission_required = "base.handle_enquiry"
    model = Enquiry
    template_name = "domain/management/enquiries/detail.html"
    context_object_name = "enquiry"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["answer_form"] = AnswerEnquiryForm()
        return context


class MarkEnquiryAnsweredView(StaffRequiredMixin, SingleObjectMixin, View):
    permission_required = "base.handle_enquiry"
    model = Enquiry
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        enquiry = self.get_object()
        form = AnswerEnquiryForm(request.POST)
        form.is_valid()
        try:
            mark_answered(enquiry, note=form.cleaned_data.get("response_note", ""), by=request.user)
        except InvalidTransitionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"{enquiry.first_name}'s enquiry is marked as answered.")
        return redirect("matchmaking:enquiries")