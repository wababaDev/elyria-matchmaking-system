from django.urls import path

from domain.matchmaking.views import dashboard_views

app_name = "matchmaking"

urlpatterns = [

        path("", dashboard_views.DashboardView.as_view(), name="dashboard"),
   
]