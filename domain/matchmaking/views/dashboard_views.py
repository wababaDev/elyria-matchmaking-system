from django.views.generic import TemplateView


class DashboardView(TemplateView):
    template_name = "domain/management/dashboard.html"