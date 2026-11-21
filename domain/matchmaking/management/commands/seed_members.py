"""
Test data for matching: 2 matchmakers, 1 admin and 12 fully approved members
(6 women seeking men, 6 men seeking women) across all tiers, each with a locked
consultation record and a complete profile. Everyone uses the same password.

    python manage.py seed_members --email you@gmail.com
    python manage.py seed_members --email you@gmail.com --password "Something-Long-1"

    # Simple logins when emails don't need to arrive (console email backend):
    python manage.py seed_members --domain elyria.test        # natasha@elyria.test, david@elyria.test, ...

    # Use matchmakers who already exist instead of creating test ones:
    python manage.py seed_members --email you@gmail.com --mm1 anisha@elyriamatchmaking.com --mm2 annastasia@elyriamatchmaking.com

Emails use "plus addressing" on the address you give, so everything lands in your inbox:
you+mm1@gmail.com, you+natasha@gmail.com, ... (Gmail and Zoho both deliver these to you).

Safe to run again: anyone who already exists is skipped. Refuses to run on production.
No emails are sent while seeding.
"""
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from domain.base.models import Groups
from domain.matchmaking.models import (
    Client,
    ClientProfile,
    Consultation,
    ConsultationRequest,
    Membership,
    MembershipPayment,
    MembershipTier,
)
from domain.matchmaking.profile_sections import CHECKS, CHIPS, FIELD_NAMES, FIELDS_BY_NAME, SCALE, SELECT, SLIDER, SHOW_WHEN

User = get_user_model()

DEFAULT_PASSWORD = "12345678"

STAFF = [
    # key, first, last, group
    ("mm1", "Test", "Matchmaker One", Groups.MATCHMAKER),
    ("mm2", "Test", "Matchmaker Two", Groups.MATCHMAKER),
    ("admin", "Test", "Admin", Groups.ADMIN),
]

# first, last, gender, seeking, age, city, religion, children (0 = none), tier, matchmaker, partner ages
MEMBERS = [
    ("Natasha", "Kabwe", "female", "man", 34, "Lusaka, Zambia", "catholic", 0, "Gold", "mm1", (32, 45)),
    ("Grace", "Lungu", "female", "man", 29, "Lusaka, Zambia", "pentecostal", 0, "Silver", "mm2", (28, 38)),
    ("Thandiwe", "Phiri", "female", "man", 41, "Ndola, Zambia", "protestant", 2, "Elite Grade", "mm1", (38, 55)),
    ("Mwila", "Chanda", "female", "man", 37, "Kitwe, Zambia", "adventist", 0, "Bronze", "mm2", (35, 48)),
    ("Chipo", "Banda", "female", "man", 45, "Lusaka, Zambia", "spiritual", 1, "Gold", "mm1", (42, 58)),
    ("Naledi", "Sibanda", "female", "man", 32, "Johannesburg, South Africa", "prefer_not", 0, "Elite Grade", "mm2", (30, 42)),
    ("David", "Mulenga", "male", "woman", 41, "Lusaka, Zambia", "catholic", 1, "Gold", "mm2", (30, 42)),
    ("Joseph", "Tembo", "male", "woman", 38, "Lusaka, Zambia", "protestant", 0, "Silver", "mm1", (28, 38)),
    ("Michael", "Zulu", "male", "woman", 45, "Ndola, Zambia", "pentecostal", 2, "Elite Grade", "mm2", (35, 46)),
    ("Brian", "Mwansa", "male", "woman", 33, "Kitwe, Zambia", "adventist", 0, "Bronze", "mm1", (27, 35)),
    ("Kelvin", "Sakala", "male", "woman", 36, "Livingstone, Zambia", "none", 0, "Gold", "mm2", (29, 38)),
    ("Samuel", "Daka", "male", "woman", 50, "Lusaka, Zambia", "african_traditional", 3, "Elite Grade", "mm1", (38, 50)),
]

OCCUPATIONS = ["Accountant", "Engineer", "Doctor", "Lawyer", "Banker", "Teacher", "Architect", "Pharmacist"]


def plus(email, tag):
    """you@gmail.com -> you+tag@gmail.com; '@elyria.test' -> tag@elyria.test"""
    local, domain = email.split("@", 1)
    return f"{local}+{tag}@{domain}" if local else f"{tag}@{domain}"


class Command(BaseCommand):
    help = "Seed matchmakers, an admin and 12 approved members with complete profiles (UAT/local only)."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Your inbox, e.g. you@gmail.com (plus-addresses are made from it)")
        parser.add_argument("--domain", help="Instead of --email: logins become name@domain, e.g. elyria.test")
        parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Password for every seeded account")
        parser.add_argument("--mm1", help="Email of an existing matchmaker to use as 'Matchmaker One'")
        parser.add_argument("--mm2", help="Email of an existing matchmaker to use as 'Matchmaker Two'")

    def handle(self, *args, **options):
        if getattr(settings, "ENVIRONMENT", "local") == "prod":
            raise CommandError("Refusing to seed test members on production.")
        password = options["password"]
        if options.get("domain"):
            email = "@" + options["domain"].strip().lower().lstrip("@")   # plus() turns this into name@domain
        elif options.get("email") and "@" in options["email"]:
            email = options["email"].strip().lower()
        else:
            raise CommandError("Give --domain elyria.test (simple logins) or --email you@gmail.com (emails reach you).")

        existing = {key: options[key] for key in ("mm1", "mm2") if options.get(key)}
        with transaction.atomic():
            staff = {}
            for key, first, last, group in STAFF:
                if key in existing:
                    staff[key] = self._existing_matchmaker(existing[key])
                elif existing and key == "admin":
                    continue  # using real staff: no test admin needed
                else:
                    staff[key] = self._staff(plus(email, key), first, last, group, password)
            created = [self._member(i, row, email, password, staff) for i, row in enumerate(MEMBERS)]

        self.stdout.write(self.style.SUCCESS(f"\nDone. Password for every seeded account: {password}\n"))
        self.stdout.write("Staff:")
        for key, user in staff.items():
            note = "existing account, own password" if key in existing else "seeded"
            self.stdout.write(f"  {key:<6} {user.full_name:<24} {user.email}  ({note})")
        self.stdout.write("\nMembers (member sign-in):")
        for (first, last, gender, seeking, age, city, _, _, tier, mm, _), was_new in zip(MEMBERS, created):
            note = "" if was_new else "  (already existed, skipped)"
            self.stdout.write(
                f"  {first + ' ' + last:<18} {gender:<6} seeks {seeking:<5} {age}  {city.split(',')[0]:<13} "
                f"{tier:<11} {mm}  {plus(email, first.lower())}{note}"
            )
        self.stdout.write("\nUpload photos yourself: sign in as a member > My Profile > photos > Save changes.")

    # ------------------------------------------------------------------ staff

    def _staff(self, email, first, last, group, password):
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            user = User.objects.create_user(email=email, password=password, first_name=first, last_name=last)
        user.groups.add(Group.objects.get(name=group))
        return user

    def _existing_matchmaker(self, email):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if not user:
            raise CommandError(f"No account with the email {email}.")
        if not user.groups.filter(name__in=[Groups.MATCHMAKER, Groups.ADMIN]).exists():
            raise CommandError(f"{email} isn't a Matchmaker or Admin.")
        return user

    # ------------------------------------------------------------------ members

    def _member(self, i, row, base_email, password, staff):
        first, last, gender, seeking, age, city, religion, kids, tier_name, mm, (age_min, age_max) = row
        email = plus(base_email, first.lower())
        if User.objects.filter(email__iexact=email).exists():
            return False

        matchmaker = staff[mm]
        tier = MembershipTier.objects.filter(name=tier_name).first() or MembershipTier.objects.first()
        now = timezone.now()
        occupation = OCCUPATIONS[i % len(OCCUPATIONS)]

        request = ConsultationRequest.objects.create(
            full_name=f"{first} {last}", preferred_name=first, gender=gender, age=age, seeking=seeking,
            relationship_status="single", location=city, nationality="Zambian", occupation=occupation,
            email=email, phone=f"+26097{1000000 + i:07d}",
            status=ConsultationRequest.Status.BECAME_MEMBER, assigned_to=matchmaker,
            fee_paid_at=now - timedelta(days=30), fee_marked_paid_by=matchmaker,
            fee_amount=1000, fee_currency="ZMW", fee_payment_method="mobile_money", fee_reference=f"SEED-{i + 1}",
        )
        Consultation.objects.create(
            request=request, scheduled_for=now - timedelta(days=21), held_at=now - timedelta(days=21),
            conducted_by=matchmaker, recording_consent="yes", identity_confirmed="yes",
            a1=f"[Test] Last relationship lasted {3 + i % 5} years; ended amicably.",
            a5=f"[Test] About {1 + i % 4} years ago. At peace with it now.",
            b2="[Test] Honesty, faith, and wanting a family.",
            b3="[Test] Family first, then faith, then career.",
            b4="[Test] We would decide together, weighing both careers.",
            b5="[Test] Jointly, with clear budgets.",
            b6="[Test] Close, but with boundaries.",
            notes=f"[Test] Warm and clear about goals. Recommended tier: {tier_name}.",
            readiness=["high", "medium"][i % 2],
            readiness_set_at=now - timedelta(days=21), readiness_set_by=matchmaker,
            record_locked_at=now - timedelta(days=21), record_locked_by=matchmaker,
        )

        user = User.objects.create_user(email=email, password=password, first_name=first, last_name=last)
        user.groups.add(Group.objects.get(name=Groups.MEMBER))
        client = Client.objects.create(
            user=user, consultation_request=request, full_name=f"{first} {last}", preferred_name=first,
            matchmaker=matchmaker,
        )

        start = date.today() - timedelta(days=20)
        months = getattr(tier, "duration_months", None) or 12
        membership = Membership.objects.create(
            client=client, tier=tier, start_date=start, end_date=start + timedelta(days=30 * months),
        )
        if getattr(tier, "price", None) is not None:
            MembershipPayment.objects.create(
                membership=membership, kind=MembershipPayment.Kind.NEW, amount=tier.price,
                currency=getattr(tier, "currency", "ZMW"), method="bank_transfer",
                reference=f"SEED-M{i + 1}", recorded_by=matchmaker,
            )

        ClientProfile.objects.create(client=client, completed_at=now - timedelta(days=10), **self._answers(i, row))
        return True

    def _answers(self, i, row):
        """Every profile answer filled in, varied per member so the filters have something to work with."""
        first, last, gender, seeking, age, city, religion, kids, tier_name, mm, (age_min, age_max) = row
        data = {}
        for name in FIELD_NAMES:
            if name in SHOW_WHEN:
                continue  # follow-up questions are set below where they apply
            field = ClientProfile._meta.get_field(name)
            kind = FIELDS_BY_NAME[name].kind
            if kind in (SLIDER, SCALE):
                data[name] = 1 + (i + len(name)) % 5
            elif kind == CHECKS:
                values = [v for v, _ in ClientProfile.CoreValue.choices if v != "other"]
                data[name] = [values[i % len(values)], values[(i + 3) % len(values)], "family"]
            elif kind in (SELECT, CHIPS) or field.choices:
                options = [v for v, _ in field.choices if v not in ("", "other")]
                data[name] = options[i % len(options)]
            elif isinstance(field, type(ClientProfile._meta.get_field("age"))):
                data[name] = 0
            else:
                data[name] = f"[Test] {field.verbose_name} for {first}."

        data.update(
            full_name=f"{first} {last}", preferred_name=first, age=age, gender=gender, seeking=seeking,
            relationship_status="single", location=city, nationality="Zambian",
            occupation=OCCUPATIONS[i % len(OCCUPATIONS)], phone=f"+26097{1000000 + i:07d}",
            religion=religion, marital_history="never_married", previous_marriages=0,
            has_children="yes" if kids else "no", wants_children=["yes", "open", "unsure"][i % 3],
            partner_gender="male" if seeking == "man" else "female",
            partner_age_min=age_min, partner_age_max=age_max,
            partner_location="Anywhere in Zambia" if "Zambia" in city else "Southern Africa",
            non_negotiables=["[Test] Must not smoke", "[Test] Must share core values"][: 1 + i % 2],
            partner_height="", partner_build="", political_involvement="",
        )
        if kids:
            data.update(children_count=kids, children_ages=", ".join(str(6 + 3 * n) for n in range(kids)),
                        children_living="Live with me")
        return data