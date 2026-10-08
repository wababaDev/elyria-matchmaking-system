from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from domain.matchmaking.forms import ConsultationRequestForm
from domain.matchmaking.services.consultation_request_service import (
    NotEligibleError,
    is_rate_limited,
    submit_consultation_request,
)


class ConsultationRequestView(FormView):
    """
    The modal and the home page form post here.
    GET (or a POST with errors) shows the form as a full page.
    """
    template_name = "domain/website/consultation_request.html"
    form_class = ConsultationRequestForm
    success_url = reverse_lazy("website:consultation-thanks")

    def post(self, request, *args, **kwargs):
        # TODO: behind nginx, read the real IP from X-Forwarded-For
        if is_rate_limited(request.META.get("REMOTE_ADDR")):
            form = self.get_form()
            form.is_valid()
            form.add_error(None, "Too many requests from your connection. Please try again later.")
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.cleaned_data.get("website"):  # honeypot filled: pretend it worked
            return redirect(self.success_url)
        try:
            submit_consultation_request(form.save(commit=False))
        except NotEligibleError as error:
            form.add_error("relationship_status", str(error))
            return self.form_invalid(form)
        # Same thank-you page whether new or a resubmission (never reveal which)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["consultation_form"] = context["form"]  # the shared partial reads this name
        return context


class ConsultationThanksView(TemplateView):
    template_name = "domain/website/consultation_thanks.html"