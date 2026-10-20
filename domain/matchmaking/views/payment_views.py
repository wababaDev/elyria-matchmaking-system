from urllib.parse import urlencode

from django import forms
from django.core.paginator import Paginator
from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.forms import staff_members
from domain.matchmaking.services.payment_service import (
    KIND_CHOICES,
    member_counts,
    payment_rows,
    payment_summary,
    staff_summary,
)


class PaymentFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Reference, name or transaction ID"}),
    )
    kind = forms.ChoiceField(
        choices=KIND_CHOICES, required=False, widget=forms.Select(attrs={"class": "form-select"})
    )
    staff = forms.ModelChoiceField(
        queryset=None, required=False, empty_label="Anyone",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staff"].queryset = staff_members()
        self.fields["staff"].label_from_instance = lambda user: user.full_name


class PaymentListView(StaffRequiredMixin, TemplateView):
    """Read-only audit of every payment. Finance and Admin."""
    permission_required = "base.view_payments"
    template_name = "domain/management/payments/list.html"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = PaymentFilterForm(self.request.GET or None)
        filters = form.cleaned_data if form.is_valid() else {}

        rows = payment_rows(
            kind=filters.get("kind") or "",
            q=filters.get("q") or "",
            staff=filters.get("staff"),
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
        )
        page = Paginator(rows, self.paginate_by).get_page(self.request.GET.get("page"))

        # Keep the filters when moving between pages
        params = self.request.GET.copy()
        params.pop("page", None)

        context.update(
            form=form,
            page_obj=page,
            payments=page.object_list,
            summary=payment_summary(rows),
            staff_rows=staff_summary(rows, date_from=filters.get("date_from"), date_to=filters.get("date_to")),
            members=member_counts(),
            filter_query=urlencode(params, doseq=True),
            is_filtered=any(filters.get(k) for k in ("q", "kind", "staff", "date_from", "date_to")),
        )
        return context