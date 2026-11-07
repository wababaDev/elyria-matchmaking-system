from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView

from domain.elite.forms import ApplyForm
from domain.elite.services.elite_service import EliteError, apply, confirm_email


class ApplyView(FormView):
    """E1: 'Apply for Consideration' from the Membership page."""
    template_name = "domain/website/elite/apply.html"
    form_class = ApplyForm
    success_url = reverse_lazy("elite:apply-sent")

    def form_valid(self, form):
        if form.cleaned_data.get("website"):
            return redirect(self.success_url)  # bot: pretend it worked
        apply(
            full_name=form.cleaned_data["full_name"],
            email=form.cleaned_data["email"],
            phone=form.cleaned_data["phone"],
        )
        return super().form_valid(form)


class ApplySentView(TemplateView):
    template_name = "domain/website/elite/apply_sent.html"


class ConfirmEmailView(View):
    def get(self, request, token):
        try:
            case = confirm_email(token)
        except EliteError as error:
            return render(request, "domain/website/elite/confirm_failed.html", {"error": str(error)}, status=400)
        return render(request, "domain/website/elite/confirmed.html", {"case": case})