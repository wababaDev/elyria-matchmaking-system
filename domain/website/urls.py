from django.urls import path

from domain.website import views
from domain.website.views import enquiry_views as enquiry_views
app_name = "website"

urlpatterns = [
    # Static pages
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("services/", views.ServicesView.as_view(), name="services"),
    path("who-we-serve/", views.WhoWeServeView.as_view(), name="who-we-serve"),
    path("membership/", views.MembershipView.as_view(), name="membership"),
    path("team/", views.TeamView.as_view(), name="team"),
    path("events/", views.EventsView.as_view(), name="events"),
    path("faq/", views.FaqView.as_view(), name="faq"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),

    
    # Consultation request form and thank-you page
    path(
        "request-consultation/",
        views.ConsultationRequestView.as_view(),
        name="consultation-request",
    ),
    path(
        "request-consultation/thank-you/",
        views.ConsultationThanksView.as_view(),
        name="consultation-thanks",
    ),

    path("enquiry/", enquiry_views.EnquiryView.as_view(), name="enquiry"),
       path("enquiry/thank-you/", enquiry_views.EnquiryThanksView.as_view(), name="enquiry-thanks"),
]
