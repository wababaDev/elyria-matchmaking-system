from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import ConsultationRequest

User = get_user_model()


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


class StaffConsultationRequestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.matchmaker = make_user("mm@x.com", Groups.MATCHMAKER)
        cls.member = make_user("m@x.com", Groups.MEMBER)

    def setUp(self):
        self.client.force_login(self.matchmaker)
        self.list_url = reverse("matchmaking:consultation-requests")

    def test_anonymous_redirected_to_staff_sign_in(self):
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertRedirects(response, f"{reverse('base:staff-sign-in')}?next={self.list_url}", fetch_redirect_response=False)

    def test_member_gets_403(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_list_shows_open_only_by_default(self):
        make_request(full_name="Open Person", email="open@x.com")
        make_request(full_name="Declined Person", email="d@x.com", status=ConsultationRequest.Status.DECLINED)
        response = self.client.get(self.list_url)
        self.assertContains(response, "Open Person")
        self.assertNotContains(response, "Declined Person")

        response = self.client.get(self.list_url, {"status": "all"})
        self.assertContains(response, "Declined Person")

    def test_search(self):
        make_request(full_name="Natasha Kabwe")
        make_request(full_name="Grace Lungu", email="grace@x.com")
        response = self.client.get(self.list_url, {"q": "grace"})
        self.assertContains(response, "Grace Lungu")
        self.assertNotContains(response, "Natasha Kabwe")

    def test_detail_page(self):
        c = make_request()
        response = self.client.get(reverse("matchmaking:consultation-request-detail", args=[c.pk]))
        self.assertContains(response, "natasha@example.com")

    def test_mark_fee_paid(self):
        c = make_request()
        self.client.post(reverse("matchmaking:consultation-request-mark-paid", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.status, ConsultationRequest.Status.FEE_PAID)
        self.assertEqual(c.fee_marked_paid_by, self.matchmaker)
        self.assertIsNotNone(c.fee_paid_at)

    def test_mark_fee_paid_twice_shows_error(self):
        c = make_request(status=ConsultationRequest.Status.FEE_PAID)
        response = self.client.post(reverse("matchmaking:consultation-request-mark-paid", args=[c.pk]), follow=True)
        self.assertContains(response, "Only requests awaiting payment")

    def test_mark_fee_paid_is_post_only(self):
        c = make_request()
        response = self.client.get(reverse("matchmaking:consultation-request-mark-paid", args=[c.pk]))
        self.assertEqual(response.status_code, 405)

    def test_assign_to_me(self):
        c = make_request()
        self.client.post(reverse("matchmaking:consultation-request-assign", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.assigned_to, self.matchmaker)

    def test_decline(self):
        c = make_request()
        self.client.post(reverse("matchmaking:consultation-request-decline", args=[c.pk]))
        c.refresh_from_db()
        self.assertEqual(c.status, ConsultationRequest.Status.DECLINED)

    def test_member_cannot_mark_paid(self):
        c = make_request()
        self.client.force_login(self.member)
        response = self.client.post(reverse("matchmaking:consultation-request-mark-paid", args=[c.pk]))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_counts(self):
        make_request()
        make_request(email="b@x.com", status=ConsultationRequest.Status.FEE_PAID)
        response = self.client.get(reverse("matchmaking:dashboard"))
        self.assertEqual(response.context["requests_this_month"], 2)
        self.assertEqual(response.context["awaiting_payment_count"], 1)