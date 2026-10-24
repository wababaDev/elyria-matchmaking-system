from django.urls import path
from django.views.generic import RedirectView

from domain.matchmaking.views import consultation_request_views as requests
from domain.matchmaking.views import settings_views as settings_
from domain.matchmaking.views import dashboard_views, enquiry_views, member_views as members, payment_views, queue_views
app_name = "matchmaking"

urlpatterns = [
    path("", dashboard_views.DashboardView.as_view(), name="dashboard"),
    path("queue/", queue_views.MyQueueView.as_view(), name="my-queue"),


    # Consultation Requests
    path("requests/", requests.ConsultationRequestListView.as_view(), name="consultation-requests"),
    path("requests/<int:pk>/", requests.ConsultationRequestDetailView.as_view(), name="consultation-request-detail"),
    path("requests/<int:pk>/mark-paid/", requests.MarkFeePaidView.as_view(), name="consultation-request-mark-paid"),
    # path("requests/<int:pk>/assign-to-me/", requests.AssignToMeView.as_view(), name="consultation-request-assign"),
    path("requests/<int:pk>/assign/", requests.AssignRequestView.as_view(), name="consultation-request-assign-to"),
    path("requests/<int:pk>/decline/", requests.DeclineRequestView.as_view(), name="consultation-request-decline"),
    path("requests/<int:pk>/book/", requests.BookConsultationView.as_view(), name="consultation-request-book"),
    path("requests/<int:pk>/notes/", requests.SaveNotesView.as_view(), name="consultation-request-notes"),
    path("requests/<int:pk>/mark-consulted/", requests.MarkConsultedView.as_view(), name="consultation-request-mark-consulted"),
    path("requests/<int:pk>/confirm-membership/", requests.ConfirmMembershipView.as_view(), name="consultation-request-confirm-membership"),


    # Settings
    path("settings/", RedirectView.as_view(pattern_name="matchmaking:settings-general"), name="settings"),
    path("settings/general/", settings_.GeneralSettingsView.as_view(), name="settings-general"),
    path("settings/staff/", settings_.StaffListView.as_view(), name="settings-staff"),
    path("settings/staff/add/", settings_.StaffCreateView.as_view(), name="settings-staff-add"),
    path("settings/staff/<int:pk>/edit/", settings_.StaffUpdateView.as_view(), name="settings-staff-edit"),
    path("settings/staff/<int:pk>/resend-invite/", settings_.StaffResendInviteView.as_view(), name="settings-staff-resend"),
    path("settings/tiers/", settings_.TierListView.as_view(), name="settings-tiers"),
    path("settings/tiers/add/", settings_.TierCreateView.as_view(), name="settings-tiers-add"),
    path("settings/tiers/<int:pk>/edit/", settings_.TierUpdateView.as_view(), name="settings-tiers-edit"),
    path("settings/documents/", settings_.DocumentsView.as_view(), name="settings-documents"),

    # Members
    path("members/", members.MemberListView.as_view(), name="members"),
    path("members/<int:pk>/", members.MemberDetailView.as_view(), name="member-detail"),
    path("members/<int:pk>/renew/", members.RenewMembershipView.as_view(), name="member-renew"),
    path("members/<int:pk>/cancel/", members.CancelMembershipView.as_view(), name="member-cancel"),
    path("members/<int:pk>/resend-link/", members.ResendSignInLinkView.as_view(), name="member-resend-link"),
    path("members/<int:pk>/reassign/", members.ReassignMatchmakerView.as_view(), name="member-reassign"),


    # Enquiries
    path("enquiries/", enquiry_views.EnquiryListView.as_view(), name="enquiries"),
    path("enquiries/<int:pk>/", enquiry_views.EnquiryDetailView.as_view(), name="enquiry-detail"),
    path("enquiries/<int:pk>/answered/", enquiry_views.MarkEnquiryAnsweredView.as_view(), name="enquiry-answered"),

    path("requests/<int:pk>/edit/", requests.ConsultationRequestEditView.as_view(), name="consultation-request-edit"),
    path("requests/<int:pk>/resend-payment/", requests.ResendPaymentInstructionsView.as_view(), name="consultation-request-resend-payment"),
    path("requests/<int:pk>/undo-paid/", requests.UndoFeePaidView.as_view(), name="consultation-request-undo-paid"),

    path("payments/", payment_views.PaymentListView.as_view(), name="payments"),
    path("members/<int:pk>/photos/<int:photo_pk>/", members.MemberPhotoView.as_view(), name="member-photo"),

    path("members/<int:pk>/change-email/", members.ChangeSignInEmailView.as_view(), name="member-change-email"),
    path("members/<int:pk>/profile.pdf", members.MemberProfilePdfView.as_view(), name="member-profile-pdf"),
]