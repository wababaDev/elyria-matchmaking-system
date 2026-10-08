from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.services.dashboard_service import dashboard_summary


class DashboardView(StaffRequiredMixin, TemplateView):
    template_name = "domain/management/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(dashboard_summary())
        return context