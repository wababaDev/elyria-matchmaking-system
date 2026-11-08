from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.elite.forms import (
    AcknowledgementForm,
    AnswerForm,
    AssignHandlerForm,
    BronzeAnswerForm,
    ChecksForm,
    ConfirmForm,
    DecisionForm,
    DocumentsReceivedForm,
    DocumentUploadForm,
    FeeForm,
    OutreachForm,
    PersonForm,
    SendAcknowledgementForm,
)
from domain.elite.models import EliteAccessLog, EliteCase, EliteDocument
from domain.elite.services import elite_service as svc

S = EliteCase.Status

LIST_TABS = [
    ("review", "Under review", [S.UNDER_REVIEW]),
    ("awaiting", "Awaiting documents", [S.AWAITING_DOCUMENTS, S.AWAITING_EMAIL]),
    ("in_progress", "In progress", [S.APPROVED, S.PAID, S.OUTREACH_SENT, S.AGREED, S.INTRODUCTION, S.BRONZE_OFFERED]),
    ("closed", "Closed", [S.DECLINED, S.CLOSED]),
    ("all", "All", None),
]


class EliteStaffMixin(StaffRequiredMixin):
    """Matchmakers and Admin. Which cases they see is decided by cases_visible_to (Admin all, handler own)."""
    permission_required = "base.manage_matching"

    def visible_cases(self):
        return svc.cases_visible_to(self.request.user)


class CaseListView(EliteStaffMixin, TemplateView):
    template_name = "domain/management/elite/case_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = self.visible_cases()
        admin = svc.is_admin(self.request.user)
        tabs = [t for t in LIST_TABS if admin or t[0] in ("in_progress", "closed", "all")]
        by_key = {key: statuses for key, _, statuses in tabs}
        show = self.request.GET.get("show")
        if show not in by_key:
            show = "review" if admin and base.filter(status=S.UNDER_REVIEW).exists() else (
                "awaiting" if admin and not base.exclude(status__in=[S.AWAITING_EMAIL, S.AWAITING_DOCUMENTS]).exists()
                else "in_progress"
            )
        qs = base if by_key[show] is None else base.filter(status__in=by_key[show])
        context.update(
            cases=qs.select_related("handler").order_by("-updated_at"),
            show=show,
            is_admin=admin,
            tabs=[(key, label, base.count() if st is None else base.filter(status__in=st).count()) for key, label, st in tabs],
        )
        return context


class CaseDetailView(EliteStaffMixin, TemplateView):
    template_name = "domain/management/elite/case_detail.html"

    def get_context_data(self, **kwargs):
        from domain.website.models import SiteDocument

        context = super().get_context_data(**kwargs)
        case = get_object_or_404(self.visible_cases().select_related("handler", "fee_recorded_by"), pk=self.kwargs["pk"])
        user = self.request.user
        svc.log_access(case, user, EliteAccessLog.Action.VIEW_CASE)
        missing = [label for kind, label in SiteDocument.Kind.choices
                   if kind in SiteDocument.ELITE_KINDS and SiteDocument.current(kind) is None]
        context.update(
            case=case,
            is_admin=svc.is_admin(user),
            can_handle=svc.can_handle(user, case),
            documents=case.documents.select_related("uploaded_by"),
            events=case.events.select_related("by"),
            access=case.access_log.select_related("user")[:20],
            upload_form=DocumentUploadForm(),
            received_form=DocumentsReceivedForm(initial={
                "nda": case.nda_received, "declaration": case.declaration_received,
                "request_form": case.request_form_received,
            }),
            checks_form=ChecksForm(initial={field: getattr(case, field) for field, _ in svc.CHECKS}),
            handler_form=AssignHandlerForm(initial={"handler": case.handler_id}),
            fee_form=FeeForm(),
            acknowledgement_blank=SiteDocument.current(SiteDocument.Kind.ELITE_ACKNOWLEDGEMENT),
            elite_price=_price_or_none(),
            person_form=PersonForm(initial={
                "name": case.person_name, "contact_type": case.person_contact_type, "contact": case.person_contact,
            } if case.has_person else None),
            outreach_form=OutreachForm(),
            ack_form=AcknowledgementForm(),
            has_indemnity_file=case.documents.filter(kind=EliteDocument.Kind.INDEMNITY).exists(),
            has_ack_file=case.documents.filter(kind=EliteDocument.Kind.ACKNOWLEDGEMENT).exists(),
            missing_documents=missing,
            just_uploaded=self.request.GET.get("uploaded") == "1",
        )
        return context


def _price_or_none():
    try:
        return svc.elite_fee()
    except svc.EliteError:
        return None


class CaseActionView(EliteStaffMixin, View):
    """POST actions. The service checks who may do what (Admin, or this case's handler)."""
    http_method_names = ["post"]
    form_class = None

    def perform(self, case, data):
        raise NotImplementedError

    def post(self, request, pk):
        case = get_object_or_404(self.visible_cases(), pk=pk)
        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, next(iter(form.errors.values()))[0])
            return redirect("elite:case-detail", case.pk)
        try:
            message, query = self.perform(case, form.cleaned_data)
        except svc.EliteError as error:
            messages.error(request, str(error))
            return redirect("elite:case-detail", case.pk)
        if message:
            messages.success(request, message)
        response = redirect("elite:case-detail", case.pk)
        if query:
            response["Location"] += query
        return response


class AdminCaseActionView(CaseActionView):
    """Part 1 steps and assigning the handler. The service refuses anyone but Admin."""


# ---------- Part 1 (Admin)

class UploadDocumentView(CaseActionView):
    form_class = DocumentUploadForm

    def perform(self, case, data):
        document = svc.add_document(case, kind=data["kind"], file=data["file"], by=self.request.user)
        return f"{document.get_kind_display()} saved to the case.", "?uploaded=1"


class DocumentsReceivedView(AdminCaseActionView):
    form_class = DocumentsReceivedForm

    def perform(self, case, data):
        case = svc.confirm_documents(case, by=self.request.user, **data)
        if case.status == S.UNDER_REVIEW:
            return "All documents received. The case is now under review.", ""
        return "Saved. The case moves to review once all three documents are ticked.", ""


class SaveChecksView(AdminCaseActionView):
    form_class = ChecksForm

    def perform(self, case, data):
        svc.save_checks(case, checks=data, by=self.request.user)
        return "Checks saved.", ""


class DecideView(AdminCaseActionView):
    form_class = DecisionForm

    def perform(self, case, data):
        svc.decide(case, decision=data["decision"], note=data["note"], by=self.request.user)
        return {
            "approve": "Approved. Next: assign the Case Handler (this emails the payment request).",
            "decline": "Declined. The client has been sent the standard message.",
            "more_info": "Your question has been emailed to the client.",
        }[data["decision"]], ""


# ---------- Part 2a

class AssignHandlerView(AdminCaseActionView):
    form_class = AssignHandlerForm

    def perform(self, case, data):
        first = case.handler_id is None
        svc.assign_handler(case, handler=data["handler"], by=self.request.user)
        extra = " The payment request and Indemnity Notice have been emailed to the client." if first else ""
        return f"{data['handler'].full_name} is the Case Handler.{extra}", ""


class RecordFeeView(CaseActionView):
    form_class = FeeForm

    def perform(self, case, data):
        svc.record_fee(case, by=self.request.user, **data)
        return "Fee recorded. It now shows on the Payments page.", ""


class IndemnityReceivedView(CaseActionView):
    form_class = ConfirmForm

    def perform(self, case, data):
        svc.confirm_indemnity(case, by=self.request.user)
        return "Indemnity Notice recorded.", ""


class RecordPersonView(CaseActionView):
    form_class = PersonForm

    def perform(self, case, data):
        _, match = svc.record_person(case, by=self.request.user, **data)
        if match == "name":
            messages.warning(self.request, "Someone with the same name is on the 'do not approach' list. Check before outreach.")
        return "The person's details are saved (encrypted).", ""


class RecordOutreachView(CaseActionView):
    form_class = OutreachForm

    def perform(self, case, data):
        case = svc.record_outreach(case, delivered=data["delivered"] == "yes", sent_on=data["sent_on"], by=self.request.user)
        if data["delivered"] == "yes":
            return f"Outreach recorded. Reply due by {case.reply_due_on:%d %b %Y}.", ""
        return "Recorded as bounced. The client has been asked for another way to reach them.", ""


class RecordAnswerView(CaseActionView):
    form_class = AnswerForm

    def perform(self, case, data):
        case = svc.record_answer(case, answer=data["answer"], person_email=data.get("person_email", ""), by=self.request.user)
        if case.status == S.AGREED:
            if data.get("person_email"):
                return "Recorded. The Introduction Acknowledgement has been emailed to them.", ""
            return "Recorded. Download the Introduction Acknowledgement below and send it to them.", ""
        return "Recorded. The client has been told and offered Bronze Membership.", ""


class SendAcknowledgementView(CaseActionView):
    form_class = SendAcknowledgementForm

    def perform(self, case, data):
        svc.send_acknowledgement(case, person_email=data["person_email"], by=self.request.user)
        return "The Introduction Acknowledgement has been emailed to them.", ""


class RecordAcknowledgementView(CaseActionView):
    form_class = AcknowledgementForm

    def perform(self, case, data):
        case = svc.record_acknowledgement(
            case, signed=data["signed"] == "yes", person_email=data.get("person_email", ""), by=self.request.user,
        )
        if case.status == S.INTRODUCTION:
            return "Acknowledgement recorded. You can now share the client's identity.", ""
        return "Recorded as not signed (treated as no response). The client has been offered Bronze.", ""


class RecordBronzeAnswerView(CaseActionView):
    form_class = BronzeAnswerForm

    def perform(self, case, data):
        accepted = data["accepted"] == "yes"
        svc.record_bronze_answer(case, accepted=accepted, by=self.request.user)
        return ("Closed. The client has been sent the link to start as a Bronze Member." if accepted
                else "Closed. The client declined the Bronze offer."), ""


class DocumentFileView(EliteStaffMixin, View):
    """Opens a case document in the browser. Every opening is logged."""

    def get(self, request, pk, document_pk):
        case = get_object_or_404(self.visible_cases(), pk=pk)
        document = get_object_or_404(EliteDocument, pk=document_pk, case=case)
        svc.log_access(case, request.user, EliteAccessLog.Action.VIEW_DOCUMENT,
                       f"{document.get_kind_display()} ({document.original_name})"[:200])
        try:
            response = FileResponse(document.file.open("rb"))
        except FileNotFoundError:
            raise Http404
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, no-store"
        return response