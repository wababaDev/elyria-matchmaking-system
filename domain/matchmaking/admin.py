from django.contrib import admin

from domain.matchmaking.models import ConsultationRequest


@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "age", "location", "status", "resubmission_count", "created_at")
    list_filter = ("status", "gender", "relationship_status")
    search_fields = ("full_name", "preferred_name", "email", "phone")
    readonly_fields = ("created_at", "updated_at", "resubmission_count", "last_resubmitted_at")