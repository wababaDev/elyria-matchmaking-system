from datetime import timedelta

from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.utils import timezone
from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.elite.forms import (
    AcknowledgementForm,
    AnswerForm,
    AssignHandlerForm,
    BronzeAnswerForm,
    CaseNoteForm,
    ChecksForm,
    CloseCaseForm,
    ConfirmForm,
    DecisionForm,
    DocumentsReceivedForm,
    DocumentUploadForm,
    ExtendWindowForm,
    FeedbackSaveForm,
    FeeForm,
    IntroductionForm,
    InfoAnswerForm,
    IntroResultForm,
    OutreachForm,
    PersonForm,
    PreparationForm,
    SendAcknowledgementForm,
)
from domain.elite.models import EliteAccessLog, EliteCase, EliteDocument, EliteInfoRequest, SuppressionEntry
from domain.elite.services import elite_service as svc
from domain.elite.services import introduction_service as intro

S = EliteCase.Status

LIST_TABS = [
    ("review", "Under review", [S.UNDER_REVIEW]),
    ("awaiting", "Awaiting documents", [S.AWAITING_DOCUMENTS, S.AWAITING_EMAIL]),
    ("in_progress", "In progress", [
        S.APPROVED, S.PAID, S.OUTREACH_SENT, S.AGREED, S.INTRODUCTION, S.INTRODUCED, S.BRONZE_OFFERED,
    ]),
    ("closed", "Closed", [S.DECLINED, S.CLOSED]),
    ("all", "All", None),
]

# Documents that come back by email at each step. The "delete it from info@" message only shows once all are in.
INBOX_DOCUMENTS = {
    S.AWAITING_DOCUMENTS: [EliteDocument.Kind.NDA, EliteDocument.Kind.DECLARATION, EliteDocument.Kind.REQUEST_FORM],
    S.APPROVED: [EliteDocument.Kind.INDEMNITY],
    S.AGREED: [EliteDocument.Kind.ACKNOWLEDGEMENT],
}


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
        abandoned, closed_due = intro.due_for_deletion() if admin else (EliteCase.objects.none(), EliteCase.objects.none())
        due_ids = set(abandoned.values_list("pk", flat=True)) | set(closed_due.values_list("pk", flat=True))
        show = self.request.GET.get("show")
        tab_counts = [(key, label, base.count() if st is None else base.filter(status__in=st).count()) for key, label, st in tabs]
        admin_tabs = [("deletion", "Due for deletion", len(due_ids)),
                      ("register", "Do not approach", SuppressionEntry.objects.count())] if admin else []
        if admin and show == "register":
            entries = list(SuppressionEntry.objects.all())
            # The reference is "ELT-0004" (built from the case id), so the id is the number after the dash
            ref_ids = {e.case_reference: int(e.case_reference.split("-")[-1])
                       for e in entries if e.case_reference.split("-")[-1].isdigit()}
            existing = set(EliteCase.objects.filter(pk__in=ref_ids.values()).values_list("pk", flat=True))
            case_ids = {ref: pk for ref, pk in ref_ids.items() if pk in existing}
            context.update(
                show=show, is_admin=admin, register_view=True, tabs=tab_counts + admin_tabs,
                entries=[{"entry": e, "case_pk": case_ids.get(e.case_reference)} for e in entries],
            )
            return context
        if admin and show == "deletion":
            context.update(
                cases=EliteCase.objects.filter(pk__in=due_ids).select_related("handler").order_by("updated_at"),
                show=show, is_admin=admin, deletion_view=True,
                abandoned_ids=set(abandoned.values_list("pk", flat=True)),
                tabs=tab_counts + admin_tabs,
            )
            return context
        if show not in by_key:
            show = "review" if admin and base.filter(status=S.UNDER_REVIEW).exists() else (
                "awaiting" if admin and not base.exclude(status__in=[S.AWAITING_EMAIL, S.AWAITING_DOCUMENTS]).exists()
                else "in_progress"
            )
        qs = base if by_key[show] is None else base.filter(status__in=by_key[show])
        waiting = EliteInfoRequest.objects.filter(case=OuterRef("pk"), answered_at__isnull=True)
        context.update(
            cases=qs.select_related("handler").annotate(waiting_for_answer=Exists(waiting)).order_by("-updated_at"),
            show=show,
            is_admin=admin,
            tabs=tab_counts + admin_tabs,
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
                "contact_other": case.person_contact_label if case.person_contact_type == EliteCase.ContactType.OTHER else "",
                "met_where": case.person_met_where, "occupation": case.person_occupation,
            } if case.has_person else None),
            outreach_form=OutreachForm(),
            ack_form=AcknowledgementForm(),
            has_indemnity_file=case.documents.filter(kind=EliteDocument.Kind.INDEMNITY).exists(),
            has_ack_file=case.documents.filter(kind=EliteDocument.Kind.ACKNOWLEDGEMENT).exists(),
            missing_documents=missing,
            just_uploaded=self.request.GET.get("uploaded") == "1",
            inbox_expected=case.status in INBOX_DOCUMENTS,
            inbox_missing=[kind.label for kind in INBOX_DOCUMENTS.get(case.status, [])
                           if not case.documents.filter(kind=kind).exists()],
            just_replied=self.request.GET.get("replied") == "1",
            info_requests=case.info_requests.select_related("asked_by", "answered_by"),
            open_info=svc.open_info_request(case),
            info_answer_form=InfoAnswerForm(),
            # Part 2b
            intro_form=IntroductionForm(initial={
                "intro_at": timezone.localtime(case.intro_at) if case.intro_at else None,
                "venue": case.intro_venue, "video_link": case.intro_video_link,
            }),
            prep_form=PreparationForm(initial={field: getattr(case, field) for field, _ in intro.PREP_FIELDS}),
            result_form=IntroResultForm(),
            close_form=CloseCaseForm(initial={"outcome": "did_not_happen" if case.status == S.INTRODUCTION else "continuing"}),
            extend_form=ExtendWindowForm(),
            note_form=CaseNoteForm(),
            feedback_cards=intro.feedback_cards(case),
            due_for_deletion=svc.is_admin(user) and any(case.pk in qs.values_list("pk", flat=True) for qs in intro.due_for_deletion()),
            deletion_due_on=(timezone.localtime(case.closed_at) + timedelta(days=svc.WIPE_AFTER_DAYS)).date() if case.closed_at else None,
            on_register=SuppressionEntry.objects.filter(case_reference=case.reference).exists(),
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


class InfoAnswerView(AdminCaseActionView):
    form_class = InfoAnswerForm

    def perform(self, case, data):
        no_answer = data["outcome"] == "no_answer"
        svc.record_info_answer(case, answer=data["answer"], file=data.get("file"), no_answer=no_answer, by=self.request.user)
        if no_answer:
            return "Recorded as no answer. You can approve or decline now.", ""
        return "Answer recorded. You can approve or decline now.", "?replied=1"


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
        _, matches = svc.record_person(case, by=self.request.user, **data)
        if matches:
            messages.warning(self.request, "Someone with the same name is on the 'do not approach' list: "
                             + "; ".join(svc.describe_match(e) for e in matches)
                             + ". Check with Admin before any outreach.")
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


# ---------- Part 2b

class ScheduleIntroductionView(CaseActionView):
    form_class = IntroductionForm

    def perform(self, case, data):
        case = intro.schedule_introduction(case, by=self.request.user, **data)
        return f"Introduction set for {timezone.localtime(case.intro_at):%d %b %Y, %H:%M}. Both have been emailed.", ""


class PreparationView(CaseActionView):
    form_class = PreparationForm

    def perform(self, case, data):
        intro.save_preparation(case, ticks=data, by=self.request.user)
        return "Preparation saved.", ""


class IntroResultView(CaseActionView):
    form_class = IntroResultForm

    def perform(self, case, data):
        case = intro.record_intro_result(case, by=self.request.user, **data)
        if case.status == S.INTRODUCED:
            return "Recorded. Next, ask both the feedback questions (Feedback tab), then close the case.", ""
        return "Recorded. Set a new date, or close the case.", ""


class CloseCaseView(CaseActionView):
    form_class = CloseCaseForm

    def perform(self, case, data):
        intro.close_case(case, by=self.request.user, **data)
        return "Case closed.", ""


class ExtendWindowView(CaseActionView):
    form_class = ExtendWindowForm

    def perform(self, case, data):
        case = intro.extend_reply_window(case, by=self.request.user, **data)
        return f"Reply window extended to {case.reply_due_on:%d %b %Y}.", ""


class SaveFeedbackView(CaseActionView):
    form_class = FeedbackSaveForm

    def perform(self, case, data):
        feedback = intro.save_feedback(case, form=data["form"], data=self.request.POST, by=self.request.user)
        flag = " Red flag: Admin will see it on the timeline." if feedback.red_flag else ""
        return f"Form {feedback.form} saved.{flag}", ""


class CaseNoteView(CaseActionView):
    form_class = CaseNoteForm

    def perform(self, case, data):
        intro.add_note(case, by=self.request.user, **data)
        return "Added to the timeline.", ""


class DeleteNowView(CaseActionView):
    form_class = ConfirmForm

    def post(self, request, pk):
        case = get_object_or_404(self.visible_cases(), pk=pk)
        try:
            message = intro.delete_now(case, by=request.user)
        except svc.EliteError as error:
            messages.error(request, str(error))
            return redirect("elite:case-detail", case.pk)
        messages.success(request, message)
        if EliteCase.objects.filter(pk=pk).exists():
            return redirect("elite:case-detail", pk)
        return redirect(reverse("elite:cases") + "?show=deletion")


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