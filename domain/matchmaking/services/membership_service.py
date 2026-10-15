from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from domain.base.models import STAFF_GROUPS, Groups
from domain.base.services.groups import in_groups
from domain.matchmaking.models import Client, ConsultationRequest, Membership, MembershipPayment
from domain.matchmaking.services.consultation_request_service import InvalidTransitionError
from notification.services.member_emails import send_member_welcome

Status = ConsultationRequest.Status


def _get_or_create_member_user(consultation_request):
    User = get_user_model()
    user = User.objects.filter(email__iexact=consultation_request.email).first()

    if user and in_groups(user, *STAFF_GROUPS):
        raise InvalidTransitionError("This email already belongs to a staff account.")
    if user and Client.objects.filter(user=user).exists():
        raise InvalidTransitionError("This person is already a client.")

    if user is None:
        first, _, last = consultation_request.full_name.strip().partition(" ")
        user = User.objects.create_user(
            email=consultation_request.email,
            password=None,  # unusable until they set one from the email link
            first_name=first,
            last_name=last,
        )
    user.groups.add(Group.objects.get(name=Groups.MEMBER))
    return user


@transaction.atomic
def confirm_membership(
    consultation_request, *, tier, start_date, end_date,
    amount, currency, method, reference="", by,
):
    consultation_request = ConsultationRequest.objects.select_for_update().get(pk=consultation_request.pk)
    if consultation_request.status != Status.CONSULTED:
        raise InvalidTransitionError("Membership can only be confirmed after the consultation.")

    user = _get_or_create_member_user(consultation_request)

    client = Client.objects.create(
        user=user,
        consultation_request=consultation_request,
        full_name=consultation_request.full_name,
        preferred_name=consultation_request.display_name,
        matchmaker=consultation_request.assigned_to or by,
    )
    membership = Membership.objects.create(
        client=client, tier=tier, start_date=start_date, end_date=end_date,
    )
    MembershipPayment.objects.create(
        membership=membership,
        kind=MembershipPayment.Kind.NEW,
        amount=amount,
        currency=currency,
        method=method,
        reference=reference,
        recorded_by=by,
    )

    consultation_request.status = Status.BECAME_MEMBER
    consultation_request.save(update_fields=["status", "updated_at"])

    transaction.on_commit(lambda: send_member_welcome(client))
    return client