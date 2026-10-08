from django.urls import path

from domain.matchmaking.views import consultation_request_views as requests
from domain.matchmaking.views import dashboard_views, queue_views

app_name = "matchmaking"

urlpatterns = [
    path("", dashboard_views.DashboardView.as_view(), name="dashboard"),
    path("queue/", queue_views.MyQueueView.as_view(), name="my-queue"),

    path("requests/", requests.ConsultationRequestListView.as_view(), name="consultation-requests"),
    path("requests/<int:pk>/", requests.ConsultationRequestDetailView.as_view(), name="consultation-request-detail"),
    path("requests/<int:pk>/mark-paid/", requests.MarkFeePaidView.as_view(), name="consultation-request-mark-paid"),
    path("requests/<int:pk>/assign-to-me/", requests.AssignToMeView.as_view(), name="consultation-request-assign"),
    path("requests/<int:pk>/assign/", requests.AssignRequestView.as_view(), name="consultation-request-assign-to"),
    path("requests/<int:pk>/decline/", requests.DeclineRequestView.as_view(), name="consultation-request-decline"),
    path("requests/<int:pk>/book/", requests.BookConsultationView.as_view(), name="consultation-request-book"),
    path("requests/<int:pk>/notes/", requests.SaveNotesView.as_view(), name="consultation-request-notes"),
    path("requests/<int:pk>/mark-consulted/", requests.MarkConsultedView.as_view(), name="consultation-request-mark-consulted"),
]