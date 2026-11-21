from django.db import models


class Groups:
    MEMBER = "Member"
    MATCHMAKER = "Matchmaker"
    ADMIN = "Admin"
    FINANCE = "Finance"


STAFF_GROUPS = [Groups.MATCHMAKER, Groups.ADMIN, Groups.FINANCE]

PERMISSIONS = [
    ("access_member_portal", "Can use the member portal"),
    ("view_consultation_request", "Can view consultation requests"),
    ("view_all_consultation_requests", "Can see every consultation request, not just assigned ones"),
    ("manage_consultation_request", "Can mark fees paid, record consultations and confirm membership"),
    ("handle_enquiry", "Can handle general enquiries"),
    ("manage_client", "Can view and update client profiles and cross-checks"),
    ("view_all_members", "Can see every member, not just their own"),
    ("manage_matching", "Can shortlist matches and record feedback and observations"),
    ("manage_event", "Can manage events"),
    ("manage_staff", "Can manage staff accounts and settings"),
    ("view_members", "Can view members"),
    ("view_payments", "Can view the payments page"),
    ("undo_payment", "Can undo a consultation fee marked as paid"),
]

_STAFF_PERMISSIONS = [
    "view_consultation_request",
    "manage_consultation_request",
    "handle_enquiry",
    "manage_client",
    "manage_matching",
    "manage_event",
]

GROUP_PERMISSIONS = {
    Groups.MEMBER: ["access_member_portal"],
    Groups.MATCHMAKER: _STAFF_PERMISSIONS + ["view_members"],
    Groups.ADMIN: _STAFF_PERMISSIONS + [
        "manage_staff",
        "view_all_consultation_requests",
        "view_all_members",
        "view_members",
        "view_payments",
        "undo_payment",
    ],
    # Read-only: sees requests, members and payments, can't change anything
    Groups.FINANCE: [
        "view_consultation_request",
        "view_all_consultation_requests",
        "view_members",
        "view_all_members",
        "view_payments",
    ],
}


class ElyriaPermissions(models.Model):
    """Holds custom permissions only. No table."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = PERMISSIONS