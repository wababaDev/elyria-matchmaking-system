from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from domain.base.mixins import AdminRequiredMixin
from domain.elite.forms import ChecksForm, DecisionForm, DocumentsReceivedForm, DocumentUploadForm
from domain.elite.models import EliteAccessLog, EliteCase, EliteDocument
from domain.elite.services.elite_service import (
    CHECKS,
    EliteError,
    add_document,
    confirm_documents,
    decide,
    log_access,
    save_checks,
)

S = EliteCase.Status

LIST_TABS = [
    ("review", "Under review", [S.UNDER_REVIEW]),
    ("awaiting", "Awaiting documents", [S.AWAITING_DOCUMENTS, S.AWAITING_EMAIL]),
    ("approved", "Approved", [S.APPROVED]),
    ("declined", "Declined", [S.DECLINED]),
    ("all", "All", None),
]


class CaseListView(AdminRequiredMixin, TemplateView):
    template_name = "domain/management/elite/case_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tabs = {key: (label, statuses) for key, label, statuses in LIST_TABS}
        show = self.request.GET.get("show")
        if show not in tabs:
            show = "review" if EliteCase.objects.filter(status=S.UNDER_REVIEW).exists() else "awaiting"
        qs = EliteCase.objects.all()
        if tabs[show][1] is not None:
            qs = qs.filter(status__in=tabs[show][1])
        counts = {key: (EliteCase.objects.filter(status__in=st).count() if st else EliteCase.objects.count())
                  for key, _, st in LIST_TABS}
        context.update(
            cases=qs.order_by("-updated_at"),
            show=show,
            tabs=[(key, label, counts[key]) for key, label, _ in LIST_TABS],
        )
        return context


class CaseDetailView(AdminRequiredMixin, TemplateView):
    template_name = "domain/management/elite/case_detail.html"

    def get_context_data(self, **kwargs):
        from domain.website.models import SiteDocument

        context = super().get_context_data(**kwargs)
        case = get_object_or_404(EliteCase, pk=self.kwargs["pk"])
        log_access(case, self.request.user, EliteAccessLog.Action.VIEW_CASE)
        missing = [label for kind, label in SiteDocument.Kind.choices
                   if kind in SiteDocument.ELITE_EMAIL_KINDS and SiteDocument.current(kind) is None]
        context.update(
            case=case,
            documents=case.documents.select_related("uploaded_by"),
            events=case.events.select_related("by"),
            access=case.access_log.select_related("user")[:20],
            upload_form=DocumentUploadForm(),
            received_form=DocumentsReceivedForm(initial={
                "nda": case.nda_received, "declaration": case.declaration_received,
                "request_form": case.request_form_received,
            }),
            checks_form=ChecksForm(initial={field: getattr(case, field) for field, _ in CHECKS}),
            missing_documents=missing,
            just_uploaded=self.request.GET.get("uploaded") == "1",
        )
        return context


class CaseActionView(AdminRequiredMixin, View):
    http_method_names = ["post"]
    form_class = None

    def perform(self, case, data, files):
        raise NotImplementedError

    def post(self, request, pk):
        case = get_object_or_404(EliteCase, pk=pk)
        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            first = next(iter(form.errors.values()))[0]
            messages.error(request, first)
            return redirect("elite:case-detail", case.pk)
        try:
            message, query = self.perform(case, form.cleaned_data, request.FILES)
        except EliteError as error:
            messages.error(request, str(error))
            return redirect("elite:case-detail", case.pk)
        messages.success(request, message)
        response = redirect("elite:case-detail", case.pk)
        if query:
            response["Location"] += query
        return response


class UploadDocumentView(CaseActionView):
    form_class = DocumentUploadForm

    def perform(self, case, data, files):
        document = add_document(case, kind=data["kind"], file=data["file"], by=self.request.user)
        return f"{document.get_kind_display()} saved to the case.", "?uploaded=1"


class DocumentsReceivedView(CaseActionView):
    form_class = DocumentsReceivedForm

    def perform(self, case, data, files):
        case = confirm_documents(case, by=self.request.user, **data)
        if case.status == S.UNDER_REVIEW:
            return "All documents received. The case is now under review.", ""
        return "Saved. The case moves to review once all three documents are ticked.", ""


class SaveChecksView(CaseActionView):
    form_class = ChecksForm

    def perform(self, case, data, files):
        save_checks(case, checks=data, by=self.request.user)
        return "Checks saved.", ""


class DecideView(CaseActionView):
    form_class = DecisionForm

    def perform(self, case, data, files):
        case = decide(case, decision=data["decision"], note=data["note"], by=self.request.user)
        return {
            "approve": "Approved. Next: assign a Case Handler and request payment.",
            "decline": "Declined. The client has been sent the standard message.",
            "more_info": "Your question has been emailed to the client.",
        }[data["decision"]], ""


class DocumentFileView(AdminRequiredMixin, View):
    """Opens a case document in the browser. Every opening is logged."""

    def get(self, request, pk, document_pk):
        document = get_object_or_404(EliteDocument.objects.select_related("case"), pk=document_pk, case_id=pk)
        log_access(document.case, request.user, EliteAccessLog.Action.VIEW_DOCUMENT,
                   f"{document.get_kind_display()} ({document.original_name})"[:200])
        try:
            response = FileResponse(document.file.open("rb"))
        except FileNotFoundError:
            raise Http404
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, no-store"
        return response