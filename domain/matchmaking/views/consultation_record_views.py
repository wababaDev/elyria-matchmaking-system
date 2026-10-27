from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.consultation_questions import BEFORE_YOU_BEGIN, SECTIONS
from domain.matchmaking.forms.consultation_record_forms import ConsultationRecordForm, ReadinessForm
from domain.matchmaking.models import Consultation
from domain.matchmaking.services.consultation_record_service import (
    OPEN_STATUSES,
    lock_consultation_record,
    missing_to_lock,
    save_consultation_record,
    set_readiness,
)
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError, requests_visible_to


class ConsultationRecordView(StaffRequiredMixin, TemplateView):
    """
    The Official Consultation Record for one request.
    A form while it's a draft; read-only once locked.
    """
    permission_required = "base.manage_consultation_request"
    template_name = "domain/management/consultation_requests/record.html"

    @cached_property
    def cr(self):
        return get_object_or_404(
            requests_visible_to(self.request.user).select_related("assigned_to"), pk=self.kwargs["pk"]
        )

    @cached_property
    def consultation(self):
        return (
            Consultation.objects.select_related("conducted_by", "record_locked_by", "readiness_set_by")
            .filter(request=self.cr)
            .first()
        )

    @property
    def editable(self):
        return self.cr.status in OPEN_STATUSES and not (self.consultation and self.consultation.is_locked)

    def get_context_data(self, form=None, **kwargs):
        context = super().get_context_data(**kwargs)
        consultation = self.consultation
        form = form or ConsultationRecordForm(instance=consultation or Consultation(request=self.cr))
        context.update(
            cr=self.cr,
            consultation=consultation,
            editable=self.editable,
            form=form,
            before_you_begin=[form[f] for f in BEFORE_YOU_BEGIN],
            sections=[
                {**s, "items": [form[f] for f in s["fields"]]}
                for s in SECTIONS
            ],
            readiness_form=ReadinessForm(),
            missing=missing_to_lock(consultation) if consultation and self.editable else [],
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")

        if action == "readiness":
            form = ReadinessForm(request.POST)
            if form.is_valid():
                try:
                    set_readiness(self.cr, readiness=form.cleaned_data["readiness"], by=request.user)
                    messages.success(request, "Readiness score recorded.")
                except InvalidTransitionError as e:
                    messages.error(request, str(e))
            return redirect("matchmaking:consultation-record", self.cr.pk)

        form = ConsultationRecordForm(request.POST, instance=self.consultation or Consultation(request=self.cr))
        if not form.is_valid():
            messages.error(request, "Some answers need correcting.")
            return self.render_to_response(self.get_context_data(form=form))

        try:
            save_consultation_record(self.cr, data=form.cleaned_data, by=request.user)
            if action == "lock":
                lock_consultation_record(self.cr, by=request.user)
                messages.success(request, "Consultation record locked. It can no longer be changed.")
            else:
                messages.success(request, "Draft saved.")
        except InvalidTransitionError as e:
            messages.error(request, str(e))
        return redirect("matchmaking:consultation-record", self.cr.pk)