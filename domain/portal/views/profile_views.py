from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import RedirectView, TemplateView

from domain.matchmaking.models import ClientProfile
from domain.matchmaking.profile_sections import CHILDREN_DETAIL, OPTIONAL, SECTIONS
from domain.matchmaking.services.profile_service import (
    MAX_NON_NEGOTIABLES,
    ProfileLockedError,
    progress,
    save_profile,
)
from domain.portal.forms.portal_forms import ProfileForm
from domain.portal.views.base import PortalMixin

# Fields that show "(optional)". Religion isn't required yet only because its list is missing.
SHOW_OPTIONAL = OPTIONAL - {"religion"}

GROUPS = [
    ("", "Your Details", None),
    ("you", "About You", "Everything in this part describes you."),
    ("partner", "About Your Ideal Partner", "Everything in this part describes the person you'd like to meet, not you."),
]


class PortalHomeView(PortalMixin, RedirectView):
    """/portal/: the profile until it's complete, then My Matches."""

    def get_redirect_url(self, *args, **kwargs):
        if self.profile.is_complete:
            return reverse("portal:matches")
        return reverse("portal:profile")


class ProfileView(PortalMixin, TemplateView):
    template_name = "domain/portal/profile/profile.html"
    portal_nav = "profile"

    def get_context_data(self, form=None, missing=None, **kwargs):
        context = super().get_context_data(**kwargs)
        form = form or ProfileForm(instance=self.profile)
        done, total = progress(self.profile)
        photos = {p.kind: p for p in self.profile.photos.all()}

        context.update(
            form=form,
            profile=self.profile,
            groups=self._groups(form),
            photo_slots=[
                {"field": form[name], "kind": kind, "label": kind.label, "photo": photos.get(kind)}
                for name, kind in ProfileForm.PHOTO_FIELDS.items()
            ],
            non_negotiables=form.non_negotiables,
            max_non_negotiables=MAX_NON_NEGOTIABLES,
            progress_done=done,
            progress_total=total,
            progress_percent=round(done / total * 100) if total else 0,
            missing=missing or [],
            ever_saved=(self.profile.updated_at - self.profile.created_at).total_seconds() > 1,
        )
        return context

    @staticmethod
    def _groups(form):
        """Sections grouped under Your Details / About You / About Your Ideal Partner."""
        has_children = form["has_children"].value() == "yes"
        groups = []
        for zone, label, banner_note in GROUPS:
            sections = []
            for section in (s for s in SECTIONS if s.zone == zone):
                fields = [
                    {
                        "spec": f,
                        "field": form[f.name],
                        "optional": f.name in SHOW_OPTIONAL,
                        "children_detail": f.name in CHILDREN_DETAIL,
                        "hidden": f.name in CHILDREN_DETAIL and not has_children,
                    }
                    for f in section.fields
                ]
                sections.append({"section": section, "fields": fields})
            groups.append({"zone": zone, "label": label, "banner_note": banner_note, "sections": sections})
        return groups

    def post(self, request, *args, **kwargs):
        # The form works on its own copy, so a rejected submission never changes the progress shown
        instance = ClientProfile.objects.get(pk=self.profile.pk)
        form = ProfileForm(request.POST, request.FILES, instance=instance)
        complete = request.POST.get("action") == "complete" and not instance.is_complete

        if not form.is_valid():
            messages.error(request, "Some answers need correcting. They're marked below.")
            return self.render_to_response(self.get_context_data(form=form))

        try:
            missing = save_profile(form.instance, photos=form.photo_uploads, complete=complete)
        except ProfileLockedError as e:
            messages.error(request, "Your profile is complete, so these answers can't be left empty.")
            return self.render_to_response(self.get_context_data(form=form, missing=e.missing))

        if complete and missing:
            messages.warning(
                request,
                "Your progress is saved. A few answers are still needed before you can mark your profile complete.",
            )
            self.profile = instance  # show exactly what was just saved
            return self.render_to_response(self.get_context_data(missing=missing))

        if complete:
            messages.success(request, "Thank you. Your responses were received, and your matchmaker has been notified.")
        else:
            messages.success(request, "Saved. You can return any time.")
        return redirect("portal:profile")