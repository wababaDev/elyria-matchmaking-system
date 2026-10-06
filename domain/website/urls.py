from django.urls import path

from domain.website import views

app_name = "website"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("services/", views.ServicesView.as_view(), name="services"),
    path("who-we-serve/", views.WhoWeServeView.as_view(), name="who-we-serve"),
    path("membership/", views.MembershipView.as_view(), name="membership"),
    path("team/", views.TeamView.as_view(), name="team"),
    path("events/", views.EventsView.as_view(), name="events"),
    path("faq/", views.FaqView.as_view(), name="faq"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
]