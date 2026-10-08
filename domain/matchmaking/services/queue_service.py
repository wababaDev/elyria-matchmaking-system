from domain.matchmaking.models import ConsultationRequest

Status = ConsultationRequest.Status


def _mine(user):
    return (
        ConsultationRequest.objects.open()
        .filter(assigned_to=user)
        .select_related("consultation")
    )


def queue_for(user):
    """A matchmaker's to-do list, grouped by what to do next (most urgent first)."""
    mine = _mine(user)
    return [
        {
            "key": "booked",
            "label": "Booked",
            "next_step": "Hold consultation",
            "items": list(mine.filter(status=Status.FEE_PAID, consultation__scheduled_for__isnull=False)
                              .order_by("consultation__scheduled_for")),
        },
        {
            "key": "to-book",
            "label": "To book",
            "next_step": "Book the consultation",
            "items": list(mine.filter(status=Status.FEE_PAID, consultation__scheduled_for__isnull=True)
                              .order_by("fee_paid_at")),
        },
        {
            "key": "to-decide",
            "label": "To decide",
            "next_step": "Confirm membership or decline",
            "items": list(mine.filter(status=Status.CONSULTED).order_by("updated_at")),
        },
        {
            "key": "awaiting-payment",
            "label": "Awaiting payment",
            "next_step": "Follow up on the fee",
            "items": list(mine.filter(status=Status.AWAITING_PAYMENT).order_by("created_at")),
        },
    ]


def queue_count(user):
    return _mine(user).count()