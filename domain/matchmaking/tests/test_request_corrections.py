from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import Consultation, ConsultationRequest

User = get_user_model()
S = ConsultationRequest.Status


def make_user(email, *groups):
    user = User.objects.create_user(email=email, password="pass12345", first_name="Test", last_name="User")
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def make_request(**overrides):
    data = {
        "full_name": "Natasha Kabwe", "preferred_name": "Natasha", "gender": "female", "age": 34,
        "seeking": "man", "relationship_status": "single", "location": "Lusaka, Zambia",
        "nationality": "Zambian", "occupation": "Accountant", "email": "natasha@example.com",
        "phone": "+260977000000",
    }
    data.update(overrides)
    return ConsultationRequest.objects.create(**data)


def edit_data(**overrides):
    data = {
        "full_name": "Natasha Kabwe", "preferred_name": "Natasha", "gender": "female", "age": "34",
        "seeking": "man", "relationship_status": "single", "relationship_status_other": "",
        "location": "Lusaka, Zambia", "nationality": "Zambian", "occupation": "Accountant",
        "email": "natasha@example.com", "phone": "+260977000000",
    }
    data.update(overrides)
    return data


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.admin = make_user("admin@x.com", Groups.ADMIN)
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)

    def url(self, name, c):
        return reverse(f"matchmaking:{name}", args=[c.pk])


class EditDetailsTests(BaseCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_corrects_details(self):
        c = make_request()
        self.client.post(self.url("consultation-request-edit", c), edit_data(full_name="Natasha K. Banda", age="35"))
        c.refresh_from_db()
        self.assertEqual(c.full_name, "Natasha K. Banda")
        self.assertEqual(c.age, 35)
        self.assertEqual(c.details_edited_by, self.admin)
        self.assertIsNotNone(c.details_edited_at)

    def test_email_is_normalised(self):
        c = make_request()
        self.client.post(self.url("consultation-request-edit", c), edit_data(email="  New@Example.COM "))
        c.refresh_from_db()
        self.assertEqual(c.email, "new@example.com")

    def test_same_rules_as_public_form(self):
        c = make_request()
        response = self.client.post(self.url("consultation-request-edit", c), edit_data(relationship_status="married"))
        self.assertContains(response, "designed exclusively for single individuals")
        c.refresh_from_db()
        self.assertEqual(c.relationship_status, "single")

    def test_age_limit_still_applies(self):
        c = make_request()
        self.client.post(self.url("consultation-request-edit", c), edit_data(age="15"))
        c.refresh_from_db()
        self.assertEqual(c.age, 34)

    def test_matchmaker_can_edit_own_request(self):
        c = make_request(assigned_to=self.matchmaker)
        self.client.force_login(self.matchmaker)
        self.client.post(self.url("consultation-request-edit", c), edit_data(phone="+260966111222"))
        c.refresh_from_db()
        self.assertEqual(c.phone, "+260966111222")

    def test_matchmaker_cannot_edit_someone_elses_request(self):
        c = make_request()
        self.client.force_login(self.matchmaker)
        response = self.client.get(self.url("consultation-request-edit", c))
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_after_becoming_member(self):
        c = make_request(status=S.BECAME_MEMBER)
        response = self.client.get(self.url("consultation-request-edit", c))
        self.assertEqual(response.status_code, 404)


class ResendPaymentInstructionsTests(BaseCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_resend_goes_to_current_email(self):
        c = make_request(email="corrected@example.com")
        self.client.post(self.url("consultation-request-resend-payment", c))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["corrected@example.com"])

    def test_only_while_awaiting_payment(self):
        c = make_request(status=S.FEE_PAID)
        response = self.client.post(self.url("consultation-request-resend-payment", c), follow=True)
        self.assertContains(response, "only be resent while")
        self.assertEqual(len(mail.outbox), 0)


class UndoFeePaidTests(BaseCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def paid(self, **overrides):
        return make_request(
            status=S.FEE_PAID, fee_paid_at=timezone.now(), fee_marked_paid_by=self.admin,
            fee_amount=1000, fee_payment_method="mobile_money", fee_reference="MM1", **overrides,
        )

    def test_admin_undoes_payment(self):
        c = self.paid()
        self.client.post(self.url("consultation-request-undo-paid", c), {"reason": "Clicked by mistake"})
        c.refresh_from_db()
        self.assertEqual(c.status, S.AWAITING_PAYMENT)
        self.assertIsNone(c.fee_paid_at)
        self.assertIsNone(c.fee_amount)
        self.assertEqual(c.fee_reference, "")
        self.assertEqual(c.fee_undone_by, self.admin)
        self.assertEqual(c.fee_undo_reason, "Clicked by mistake")

    def test_reason_required(self):
        c = self.paid()
        self.client.post(self.url("consultation-request-undo-paid", c), {"reason": ""})
        c.refresh_from_db()
        self.assertEqual(c.status, S.FEE_PAID)

    def test_matchmaker_cannot_undo(self):
        c = self.paid(assigned_to=self.matchmaker)
        self.client.force_login(self.matchmaker)
        response = self.client.post(self.url("consultation-request-undo-paid", c), {"reason": "x"})
        self.assertEqual(response.status_code, 403)

    def test_blocked_once_consultation_started(self):
        c = self.paid()
        Consultation.objects.create(request=c, scheduled_for=timezone.now())
        response = self.client.post(self.url("consultation-request-undo-paid", c), {"reason": "x"}, follow=True)
        self.assertContains(response, "already been booked")
        c.refresh_from_db()
        self.assertEqual(c.status, S.FEE_PAID)

    def test_only_paid_requests(self):
        c = make_request()
        response = self.client.post(self.url("consultation-request-undo-paid", c), {"reason": "x"}, follow=True)
        self.assertContains(response, "Only requests marked as paid")