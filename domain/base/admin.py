from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from domain.base.models import Profile, User


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ("phone_number", "job_title")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "group_list", "is_active")
    list_filter = ("groups", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Groups", {"fields": ("groups",)}),
        ("Advanced", {
            "classes": ("collapse",),
            "fields": ("is_active", "is_staff", "is_superuser", "user_permissions"),
        }),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2", "groups"),
        }),
    )
    filter_horizontal = ("groups", "user_permissions")

    def get_inlines(self, request, obj):
        # Only on edit: on "add", the signal already creates the profile
        return [ProfileInline] if obj else []

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="Groups")
    def group_list(self, obj):
        return ", ".join(g.name for g in obj.groups.all()) or "—"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "job_title", "phone_number", "created_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_select_related = ("user",)