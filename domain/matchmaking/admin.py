from django.contrib import admin

from domain.matchmaking.models import Consultation, ConsultationRequest


class ConsultationInline(admin.StackedInline):
    model = Consultation
    can_delete = False
    extra = 0


@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "age", "location", "status", "assigned_to", "created_at")
    list_filter = ("status", "assigned_to", "gender", "relationship_status")
    search_fields = ("full_name", "preferred_name", "email", "phone")
    readonly_fields = ("created_at", "updated_at", "resubmission_count", "last_resubmitted_at")
    inlines = [ConsultationInline]