from django import template

register = template.Library()

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