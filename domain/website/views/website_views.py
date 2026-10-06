from django.views.generic import TemplateView


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