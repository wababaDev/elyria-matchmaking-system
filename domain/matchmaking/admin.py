from django.contrib import admin

from domain.matchmaking.models import Consultation, ConsultationRequest
from domain.matchmaking.models import (
    Client, Consultation, ConsultationRequest, Membership, MembershipPayment,
)
from domain.matchmaking.models import MembershipTier

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

class MembershipPaymentInline(admin.TabularInline):
    model = MembershipPayment
    extra = 0


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("client", "tier", "status", "start_date", "end_date")
    list_filter = ("tier", "status")
    inlines = [MembershipPaymentInline]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "matchmaker", "created_at")
    search_fields = ("full_name", "preferred_name", "user__email")

@admin.register(MembershipTier)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "currency", "duration_months", "display_order", "is_active")
    list_editable = ("price", "currency", "duration_months", "display_order", "is_active")