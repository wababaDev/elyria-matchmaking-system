from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.base.models import Groups
from domain.base.services.groups import create_groups_and_permissions
from domain.matchmaking.models import (
    Client,
    ClientProfile,
    ConsultationRequest,
    MatchAccessLog,
    Membership,
    MembershipTier,
    Pairing,
)
from domain.matchmaking.services.pairing_service import age_band, candidates_for

User = get_user_model()
_n = 0


def make_user(email, *groups):
    user = User.objects.create_user(
        email=email,
        password="pass12345",
        first_name=email.split("@")[0].title(),
        last_name="User",
    )
    user.groups.add(*Group.objects.filter(name__in=groups))
    return user


def make_member(full_name, *, gender, seeking, matchmaker, age=35, complete=True):
    global _n
    _n += 1
    email = f"member{_n}@example.com"
    first = full_name.split()[0]
    request = ConsultationRequest.objects.create(
        full_name=full_name,
        preferred_name=first,
        gender=gender,
        age=age,
        seeking=seeking,
        relationship_status="single",
        location="Lusaka, Zambia",
        nationality="Zambian",
        occupation="Accountant",
        email=email,
        phone="+260977000000",
        status=ConsultationRequest.Status.BECAME_MEMBER,
    )
    client = Client.objects.create(
        user=make_user(email, Groups.MEMBER),
        consultation_request=request,
        full_name=full_name,
        preferred_name=first,
        matchmaker=matchmaker,
    )
    Membership.objects.create(
        client=client,
        tier=MembershipTier.objects.get(name="Gold"),
        start_date=date(2026, 1, 1),
        end_date=date(2099, 1, 1),
    )
    ClientProfile.objects.create(
        client=client,
        full_name=full_name,
        preferred_name=first,
        gender=gender,
        seeking=seeking,
        age=age,
        location="Lusaka, Zambia",
        completed_at=timezone.now() if complete else None,
    )
    return client


class PairingCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_groups_and_permissions()
        cls.anisha = make_user("anisha@x.com", Groups.MATCHMAKER)
        cls.annastasia = make_user("annastasia@x.com", Groups.MATCHMAKER)
        cls.finance = make_user("fin@x.com", Groups.FINANCE)

        cls.natasha = make_member(
            "Natasha Kabwe", gender="female", seeking="man", matchmaker=cls.anisha
        )
        cls.david = make_member(
            "David Mulenga",
            gender="male",
            seeking="woman",
            matchmaker=cls.annastasia,
            age=41,
        )
        cls.joseph = make_member(
            "Joseph Banda", gender="male", seeking="woman", matchmaker=cls.anisha
        )
        cls.grace = make_member(
            "Grace Lungu", gender="female", seeking="man", matchmaker=cls.annastasia
        )
        cls.peter = make_member(
            "Peter Phiri",
            gender="male",
            seeking="woman",
            matchmaker=cls.anisha,
            complete=False,
        )

    def as_user(self, user):
        self.client.force_login(user)

    def propose(self, member, candidate, by):
        self.as_user(by)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("matchmaking:pairing-propose", args=[member.pk]),
                {
                    "candidate": candidate.pk,
                    "note": "You both value family.",
                    "profession": "Works in engineering",
                    "location": "Lusaka",
                },
            )
        return Pairing.objects.filter(client_a=member, client_b=candidate).first()

    def portal(self, member):
        self.as_user(member.user)
        return self.client.get(reverse("portal:matches"))

    def decide(self, member, pairing, decision):
        self.as_user(member.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("portal:match-decision", args=[pairing.pk]),
                {"decision": decision},
            )
        pairing.refresh_from_db()


class CandidateTests(PairingCase):
    def test_only_fitting_complete_active_members(self):
        found = set(candidates_for(self.natasha))
        self.assertEqual(
            found, {self.david, self.joseph}
        )  # not Grace (female), not Peter (incomplete)

    def test_find_page_only_for_own_members_and_is_logged(self):
        url = reverse("matchmaking:find-match", args=[self.natasha.pk])
        self.as_user(self.annastasia)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.as_user(self.finance)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.as_user(self.anisha)
        response = self.client.get(url)
        self.assertContains(response, "Propose pairing")
        self.assertNotContains(
            response, "David Mulenga"
        )  # another matchmaker's member: first name only
        self.assertContains(response, "Joseph Banda")  # her own member: full name
        self.assertTrue(
            MatchAccessLog.objects.filter(user=self.anisha, action="search").exists()
        )

    def test_age_band(self):
        self.assertEqual(age_band(33), "Early 30s")
        self.assertEqual(age_band(34), "Mid 30s")
        self.assertEqual(age_band(45), "Mid 40s")
        self.assertEqual(age_band(48), "Late 40s")


class SameMatchmakerTests(PairingCase):
    def test_no_approval_needed_and_member_sees_card(self):
        pairing = self.propose(self.natasha, self.joseph, self.anisha)
        self.assertEqual(pairing.approval, Pairing.Approval.NOT_NEEDED)
        response = self.portal(self.natasha)
        self.assertContains(response, "Joseph")
        self.assertContains(response, "Works in engineering")
        self.assertNotContains(response, "Banda")  # never the surname


class CrossMatchmakerTests(PairingCase):
    def test_full_journey(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.assertEqual(pairing.approval, Pairing.Approval.PENDING)
        self.assertIn("annastasia@x.com", mail.outbox[-1].to)

        # Nobody sees anything before approval
        self.assertNotContains(self.portal(self.natasha), "David")
        self.assertNotContains(self.portal(self.david), "Natasha")

        # Approval 1: David's matchmaker approves. Still nobody sees anything.
        self.as_user(self.annastasia)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("matchmaking:pairing-approve", args=[pairing.pk]),
                {"approve": "yes"},
            )
        self.assertNotContains(self.portal(self.natasha), "David")
        self.assertNotContains(self.portal(self.david), "Natasha")

        # Approval 2: Natasha's matchmaker sees David's full profile, then presents him to Natasha
        self.as_user(self.anisha)
        self.assertEqual(
            self.client.get(
                reverse("matchmaking:pairing-profile", args=[pairing.pk, self.david.pk])
            ).status_code,
            200,
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("matchmaking:pairing-present-a", args=[pairing.pk]),
                {
                    "note": "You both value family.",
                    "profession": "Works in engineering",
                    "location": "Lusaka",
                },
            )
        self.assertContains(self.portal(self.natasha), "David")
        self.assertNotContains(self.portal(self.david), "Natasha")

    def test_other_matchmaker_cannot_present_or_approve_for_someone_elses_member(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.as_user(self.anisha)
        self.client.post(
            reverse("matchmaking:pairing-approve", args=[pairing.pk]),
            {"approve": "yes"},
        )
        pairing.refresh_from_db()
        self.assertEqual(pairing.approval, Pairing.Approval.PENDING)

    def test_declined_approval_closes_and_nobody_sees_anything(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.as_user(self.annastasia)
        self.client.post(
            reverse("matchmaking:pairing-approve", args=[pairing.pk]),
            {"approve": "no", "reason": "Not suitable"},
        )
        pairing.refresh_from_db()
        self.assertFalse(pairing.is_open)
        self.assertNotContains(self.portal(self.natasha), "David")


class DeclineTests(PairingCase):
    def test_a_says_no_then_b_is_never_shown(self):
        pairing = self.propose(self.natasha, self.joseph, self.anisha)
        self.decide(self.natasha, pairing, "not_interested")
        self.assertFalse(pairing.is_open)
        self.assertNotContains(
            self.portal(self.natasha), "Joseph"
        )  # removed from her view
        self.assertNotContains(self.portal(self.joseph), "Natasha")  # never shown
        self.assertTrue(
            Pairing.objects.filter(pk=pairing.pk).exists()
        )  # kept on record

    def test_b_says_no_then_a_sees_neutral_message(self):
        pairing = self.propose(self.natasha, self.joseph, self.anisha)
        self.decide(self.natasha, pairing, "interested")
        self.as_user(self.anisha)
        self.client.post(
            reverse("matchmaking:pairing-present", args=[pairing.pk]),
            {"note": "Kind and steady."},
        )
        self.decide(self.joseph, pairing, "not_interested")
        response = self.portal(self.natasha)
        self.assertContains(response, "This introduction will not go ahead.")
        self.assertNotContains(response, "not interested")


class PairingListTests(PairingCase):
    def test_type_and_waiting_on_me(self):
        self.propose(self.natasha, self.joseph, self.anisha)  # both Anisha's
        self.propose(self.natasha, self.david, self.anisha)  # David is Annastasia's
        url = reverse("matchmaking:pairings")

        self.as_user(self.anisha)
        response = self.client.get(url + "?show=open")
        self.assertContains(response, "Between your members")
        self.assertContains(response, "Waiting for Annastasia User to approve")

        self.as_user(self.annastasia)
        response = self.client.get(url + "?show=me")
        self.assertContains(response, "Received")
        self.assertContains(
            response, "Approve: Anisha User wants to show David to their member"
        )


class FindMatchChildrenTests(PairingCase):
    def test_not_open_to_children_starts_without_them(self):
        ClientProfile.objects.filter(client=self.natasha).update(
            open_to_partner_children="no"
        )
        ClientProfile.objects.filter(client=self.joseph).update(has_children="yes")
        ClientProfile.objects.filter(client=self.david).update(has_children="no")

        self.as_user(self.anisha)
        response = self.client.get(
            reverse("matchmaking:find-match", args=[self.natasha.pk])
        )
        self.assertNotContains(response, "Joseph Banda")
        self.assertContains(response, 'data-name="David"')


class PhotoPrivacyTests(PairingCase):
    def test_member_cannot_fetch_photo_of_someone_not_presented(self):
        self.as_user(self.natasha.user)
        response = self.client.get(reverse("portal:match-photo", args=[self.david.pk]))
        self.assertEqual(response.status_code, 404)


class PortalCountTests(PairingCase):
    def test_count_on_my_matches(self):
        from domain.matchmaking.services.pairing_service import matches_to_answer

        pairing = self.propose(self.natasha, self.joseph, self.anisha)
        self.assertEqual(matches_to_answer(self.natasha), 1)
        self.assertEqual(matches_to_answer(self.joseph), 0)  # not presented to him yet
        self.assertContains(
            self.portal(self.natasha), "1 introduction waiting for your answer"
        )

        self.decide(self.natasha, pairing, "interested")
        self.assertEqual(matches_to_answer(self.natasha), 0)

    def test_nothing_before_approval(self):
        self.propose(
            self.natasha, self.david, self.anisha
        )  # waiting for David's matchmaker
        self.assertEqual(self.portal(self.natasha).context["matches_to_answer"], 0)


class AdminAsMatchmakerTests(PairingCase):
    def test_admin_with_own_members_sees_her_side(self):
        boss = make_user("boss@x.com", Groups.ADMIN)
        chipo = make_member(
            "Chipo Mwale", gender="female", seeking="man", matchmaker=boss
        )
        self.propose(
            self.joseph, chipo, self.anisha
        )  # Anisha's member -> Admin's member
        self.propose(
            self.natasha, self.david, self.anisha
        )  # nothing to do with the Admin's members

        self.as_user(boss)
        response = self.client.get(reverse("matchmaking:pairings") + "?show=me")
        self.assertContains(response, "Chipo Mwale")  # her member, in the Member column
        self.assertContains(response, "Received")
        self.assertContains(
            response, "Approve: Anisha User wants to show Chipo to their member"
        )
        self.assertNotContains(
            response, "wants to show David"
        )  # Annastasia's to approve, not hers

        response = self.client.get(reverse("matchmaking:pairings") + "?show=others")
        self.assertContains(
            response, "Other matchmakers"
        )  # still visible to Admin, just not "on me"


class FullProfileAccessTests(PairingCase):
    """Natasha (Anisha's) proposed to David (Annastasia's)."""

    def profile_url(self, pairing, client):
        return reverse("matchmaking:pairing-profile", args=[pairing.pk, client.pk])

    def approve(self, pairing):
        self.as_user(self.annastasia)
        self.client.post(
            reverse("matchmaking:pairing-approve", args=[pairing.pk]),
            {"approve": "yes"},
        )

    def test_receiving_matchmaker_sees_proposed_member_without_contact_details(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.as_user(self.annastasia)
        response = self.client.get(self.profile_url(pairing, self.natasha))
        self.assertContains(response, "Natasha's profile")
        self.assertContains(response, "Official Consultation Record")
        self.assertNotContains(response, "Kabwe")  # full name hidden
        self.assertTrue(
            MatchAccessLog.objects.filter(
                user=self.annastasia, client=self.natasha
            ).exists()
        )

    def test_proposing_matchmaker_sees_other_member_only_after_approval(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.as_user(self.anisha)
        self.assertEqual(
            self.client.get(self.profile_url(pairing, self.david)).status_code, 404
        )
        self.approve(pairing)
        self.as_user(self.anisha)
        self.assertContains(
            self.client.get(self.profile_url(pairing, self.david)), "David's profile"
        )

    def test_member_sees_nothing_until_second_approval(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.approve(pairing)
        self.assertNotContains(self.portal(self.natasha), "David")
        self.as_user(self.anisha)
        response = self.client.get(reverse("matchmaking:pairings") + "?show=me")
        self.assertContains(
            response, "Approved: review David&#x27;s profile, then present to Natasha"
        )

    def test_admin_gets_the_same_page(self):
        boss = make_user("boss@x.com", Groups.ADMIN)
        pairing = self.propose(self.natasha, self.david, self.anisha)
        self.as_user(boss)
        self.assertContains(
            self.client.get(self.profile_url(pairing, self.natasha)),
            "Natasha's profile",
        )

    def test_not_for_finance_and_not_after_close(self):
        pairing = self.propose(self.natasha, self.david, self.anisha)
        url = self.profile_url(pairing, self.natasha)
        self.as_user(self.finance)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.as_user(self.annastasia)
        self.client.post(
            reverse("matchmaking:pairing-approve", args=[pairing.pk]),
            {"approve": "no", "reason": "Not suitable"},
        )
        self.assertEqual(self.client.get(url).status_code, 404)


class FindMatchChildrenTests(PairingCase):
    def test_not_open_to_children_starts_without_them(self):
        ClientProfile.objects.filter(client=self.natasha).update(
            open_to_partner_children="no"
        )
        ClientProfile.objects.filter(client=self.joseph).update(has_children="yes")
        ClientProfile.objects.filter(client=self.david).update(has_children="no")

        self.as_user(self.anisha)
        response = self.client.get(
            reverse("matchmaking:find-match", args=[self.natasha.pk])
        )
        self.assertNotContains(response, "Joseph Banda")
        self.assertContains(response, 'data-name="David"')
