from django.views.generic import TemplateView
from domain.website.models import SiteDocument


class HomeView(TemplateView):
    template_name = "domain/website/home.html"


class AboutView(TemplateView):
    template_name = "domain/website/about.html"


class ServicesView(TemplateView):
    template_name = "domain/website/services.html"


class WhoWeServeView(TemplateView):
    template_name = "domain/website/who_we_serve.html"


class MembershipView(TemplateView):
    template_name = "domain/website/membership.html"


class TeamView(TemplateView):
    template_name = "domain/website/team.html"


class EventsView(TemplateView):
    template_name = "domain/website/events.html"


class FaqView(TemplateView):
    template_name = "domain/website/faq.html"


class PrivacyView(TemplateView):
    template_name = "domain/website/privacy.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["privacy_document"] = SiteDocument.current(SiteDocument.Kind.PRIVACY_POLICY)
        return context