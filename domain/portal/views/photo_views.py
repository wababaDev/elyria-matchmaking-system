from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views import View

from domain.matchmaking.models import ProfilePhoto
from domain.portal.views.base import PortalMixin


class OwnPhotoView(PortalMixin, View):
    """A member can only ever open their own photos."""

    def get(self, request, pk):
        photo = get_object_or_404(ProfilePhoto, pk=pk, profile__client__user=request.user)
        try:
            response = FileResponse(photo.image.open("rb"))
        except FileNotFoundError:
            raise Http404
        response["Cache-Control"] = "private, no-store"
        return response