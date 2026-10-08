from django.urls import path
from domain.matchmaking.views import consultation_request_views as requests
from domain.matchmaking.views import dashboard_views

app_name = "matchmaking"

urlpatterns = [
    path("", dashboard_views.DashboardView.as_view(), name="dashboard"),
    path(
        "requests/",
        requests.ConsultationRequestListView.as_view(),
        name="consultation-requests",
    ),
    path(
        "requests/<int:pk>/",
        requests.ConsultationRequestDetailView.as_view(),
        name="consultation-request-detail",
    ),
    path(
        "requests/<int:pk>/mark-paid/",
        requests.MarkFeePaidView.as_view(),
        name="consultation-request-mark-paid",
    ),
    path(
        "requests/<int:pk>/assign-to-me/",
        requests.AssignToMeView.as_view(),
        name="consultation-request-assign",
    ),
    path(
        "requests/<int:pk>/decline/",
        requests.DeclineRequestView.as_view(),
        name="consultation-request-decline",
    ),
]
