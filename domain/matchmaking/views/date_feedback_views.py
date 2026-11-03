from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms.date_feedback_forms import DateFeedbackForm
from domain.matchmaking.models import Client
from domain.matchmaking.models.date_feedback import DateFeedback
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from domain.matchmaking.services.date_feedback_service import (
    can_record_feedback,
    feedback_for,
    new_feedback,
    save_feedback,
)
from domain.matchmaking.services.pairing_service import pairings_visible_to


class DateFeedbackView(StaffRequiredMixin, TemplateView):
    """
    Add (pairing + member in the URL) or edit (feedback in the URL) one member's feedback for one date.
    Only that member's own matchmaker, or Admin.
    """
    permission_required = "base.manage_matching"
    template_name = "domain/management/pairings/feedback_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if "feedback_pk" in kwargs:
            self.feedback = get_object_or_404(
                DateFeedback.objects.select_related("pairing", "client"), pk=kwargs["feedback_pk"]
            )
            self.pairing, self.member = self.feedback.pairing, self.feedback.client
        else:
            self.pairing = get_object_or_404(pairings_visible_to(request.user), pk=kwargs["pk"])
            self.member = get_object_or_404(Client, pk=kwargs["client_pk"])
            self.feedback = new_feedback(self.pairing, self.member)
        if not can_record_feedback(request.user, self.pairing, self.member):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def back_url(self):
        return reverse("matchmaking:member-detail", args=[self.member.pk]) + "#pairings"

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        other = self.pairing.other(self.member)
        context.update(
            form=form or DateFeedbackForm(instance=self.feedback),
            feedback=self.feedback,
            pairing=self.pairing,
            member=self.member,
            other=other,
            other_profile=getattr(other, "profile", None),
            earlier=feedback_for(self.pairing, self.member).exclude(pk=self.feedback.pk),
            back_url=self.back_url(),
            tab_labels=["Introduction", "Went ahead?", f"What {self.member.preferred_name} says", "Your record", "Outcome"],
        )
        return context

    def post(self, request, *args, **kwargs):
        form = DateFeedbackForm(request.POST, instance=self.feedback)
        if not form.is_valid():
            messages.error(request, "Please check the highlighted fields.")
            return self.render_to_response(self.get_context_data(form=form))
        try:
            feedback = save_feedback(form.save(commit=False), by=request.user)
        except InvalidTransitionError as e:
            messages.error(request, str(e))
            return redirect(self.back_url())
        messages.success(request, f"Feedback for date {feedback.date_number} saved ({feedback.get_outcome_display()}).")
        return redirect(self.back_url())