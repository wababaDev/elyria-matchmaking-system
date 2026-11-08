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


class FeedbackView(View):
    """
    A person's own feedback form, opened from the private link in their email. No login.
    Shows only their form: never names, never details of the case.
    """
    template_name = "domain/website/elite/feedback.html"

    def _render(self, request, feedback, errors=None, data=None, status=200):
        from domain.elite.forms.feedback_forms import FORMS

        import json

        posted = {k: v for k, v in (data or {}).items() if k != "csrfmiddlewaretoken"}
        return render(request, self.template_name, {
            "feedback": feedback, "questions": FORMS[feedback.form], "errors": errors or {},
            "data_json": json.dumps(posted).replace("<", "\\u003c"),
            "scale5": range(1, 6), "scale10": range(0, 11),
        }, status=status)

    def _unavailable(self, request, message):
        return render(request, "domain/website/elite/feedback_done.html", {"message": message}, status=200)

    def get(self, request, token):
        from domain.elite.services.introduction_service import feedback_for_token

        feedback = feedback_for_token(token)
        if feedback is None or not feedback.sent_at:
            return self._unavailable(request, "This link isn't valid.")
        if feedback.completed_at:
            return self._unavailable(request, "Thank you, this form has already been completed.")
        if not feedback.is_open:
            return self._unavailable(request, "This form has closed. If you'd still like to share feedback, simply reply to our email.")
        return self._render(request, feedback)

    def post(self, request, token):
        from domain.elite.services.introduction_service import submit_feedback

        try:
            feedback, errors = submit_feedback(token, request.POST)
        except EliteError as error:
            return self._unavailable(request, str(error))
        if errors:
            return self._render(request, feedback, errors, request.POST, status=400)
        return self._unavailable(request, "Thank you. Your feedback has been received, and is seen only by Elyria.")