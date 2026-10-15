from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from domain.base.http import client_ip
from domain.matchmaking.forms import EnquiryForm
from domain.matchmaking.models import MembershipTier
from domain.matchmaking.services.consultation_request_service import is_rate_limited
from domain.matchmaking.services.enquiry_service import submit_enquiry


class EnquiryView(FormView):
    """The Learn More modal posts here; the full page only shows if there are errors."""
    template_name = "domain/website/enquiry.html"
    form_class = EnquiryForm

    def post(self, request, *args, **kwargs):
        if is_rate_limited(client_ip(request), scope="enquiry"):
            form = self.get_form()
            form.is_valid()
            form.add_error(None, "Too many requests from your connection. Please try again later.")
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.cleaned_data.get("website"):  # honeypot
            return redirect("website:enquiry-thanks")
        enquiry = submit_enquiry(form.save(commit=False))
        url = reverse("website:enquiry-thanks")
        return redirect(f"{url}?tier={enquiry.tier.pk}" if enquiry.tier else url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["enquiry_form"] = context["form"]
        return context


class EnquiryThanksView(TemplateView):
    template_name = "domain/website/enquiry_thanks.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tier_id = self.request.GET.get("tier", "")
        context["tier"] = MembershipTier.objects.filter(pk=tier_id).first() if tier_id.isdigit() else None
        return context