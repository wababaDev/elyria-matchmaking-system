from django import template

register = template.Library()

# Status badges for consultation requests

STATUS_BADGES = {
    "awaiting_payment": "status-awaiting",
    "fee_paid": "status-paid",
    "consulted": "status-complete",
    "became_member": "status-complete",
    "declined": "status-declined",
    "closed": "bg-light text-muted",
}


@register.filter
def status_badge(status):
    return STATUS_BADGES.get(status, "bg-light text-muted")


# Membership badges for members

MEMBER_BADGES = {
    "active": ("bg-success-transparent", "Active"),
    "expiring": ("bg-warning-transparent", "Expiring soon"),
    "expired": ("bg-danger-transparent", "Expired"),
    "cancelled": ("bg-light text-muted", "Cancelled"),
}


@register.filter
def member_badge(display_status):
    return MEMBER_BADGES.get(display_status, ("bg-light", ""))[0]


@register.filter
def member_status_label(display_status):
    return MEMBER_BADGES.get(display_status, ("", display_status))[1]