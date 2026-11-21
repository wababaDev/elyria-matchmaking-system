from django.urls import path

from domain.portal.views.account_views import AccountView
from domain.portal.views.match_views import MatchesView
from domain.portal.views.photo_views import OwnPhotoView
from domain.portal.views.profile_views import PortalHomeView, ProfileView
from domain.portal.views.match_views import MatchDecisionView, MatchesView, MatchPhotoView

app_name = "portal"

urlpatterns = [
    path("", PortalHomeView.as_view(), name="home"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("matches/", MatchesView.as_view(), name="matches"),
    path("account/", AccountView.as_view(), name="account"),
    path("photos/<int:pk>/", OwnPhotoView.as_view(), name="photo"),
    path("matches/<int:pk>/decide/", MatchDecisionView.as_view(), name="match-decision"),
    path("matches/photo/<int:client_pk>/", MatchPhotoView.as_view(), name="match-photo")
]