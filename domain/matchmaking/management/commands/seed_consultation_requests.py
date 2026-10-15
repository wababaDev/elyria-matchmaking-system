import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.services.consultation_request_service import (
    assign_request,
    mark_fee_paid,
    submit_consultation_request,
)
from domain.matchmaking.services.consultation_service import (
    book_consultation,
    mark_consulted,
    save_consultation_notes,
)

R = ConsultationRequest

FIRST_NAMES = {
    "female": ["Natasha", "Grace", "Ruth", "Chipo", "Mwila", "Thandiwe", "Bupe", "Nalukui", "Esther", "Mutinta"],
    "male": ["David", "Joseph", "Peter", "Mulenga", "Chanda", "Bwalya", "Kondwani", "Michael", "Tafadzwa", "Daniel"],
}
LAST_NAMES = ["Banda", "Phiri", "Mwale", "Zulu", "Tembo", "Lungu", "Mulenga", "Kabwe", "Sakala", "Chilufya", "Ngoma"]
PLACES = [
    "Lusaka, Zambia", "Lusaka, Zambia", "Ndola, Zambia", "Kitwe, Zambia", "Livingstone, Zambia",
    "Johannesburg, South Africa", "London, UK", "Lilongwe, Malawi", "Harare, Zimbabwe",
]
NATIONALITIES = ["Zambian"] * 6 + ["Malawian", "Zimbabwean", "South African", "British"]
OCCUPATIONS = [
    "Accountant", "Engineer", "Doctor", "Lawyer", "Teacher", "Banker", "Entrepreneur",
    "Pharmacist", "Architect", "Civil servant", "Nurse", "Consultant",
]
STAGES = ["new", "paid", "booked", "consulted"]


def fake_request(suffix):
    gender = random.choice(["female", "male"])
    first, last = random.choice(FIRST_NAMES[gender]), random.choice(LAST_NAMES)
    return R(
        full_name=f"{first} {last}",
        preferred_name=random.choice(["", first]),
        gender=gender,
        seeking="man" if gender == "female" else "woman",
        age=random.randint(24, 60),
        relationship_status=random.choice(
            [R.RelationshipStatus.SINGLE] * 4 + [R.RelationshipStatus.DIVORCED, R.RelationshipStatus.WIDOWED]
        ),
        location=random.choice(PLACES),
        nationality=random.choice(NATIONALITIES),
        occupation=random.choice(OCCUPATIONS),
        email=f"{first}.{last}.{suffix}@example.com".lower(),
        phone=f"+26097{random.randint(1_000_000, 9_999_999)}",
    )


class Command(BaseCommand):
    help = "DEV ONLY: create fake consultation requests, submitted the same way the public form does."

    def add_arguments(self, parser):
        parser.add_argument("count", type=int, nargs="?", default=10)
        parser.add_argument("--assign-to", metavar="EMAIL", help="Assign them all to this staff member.")
        parser.add_argument(
            "--spread", action="store_true",
            help="Move them along randomly: fee paid, booked, consulted. Needs --assign-to.",
        )
        parser.add_argument("--no-email", action="store_true", help="Don't print the email lines.")

    def handle(self, *args, count, assign_to, spread, no_email, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to run with DEBUG off. This is for local testing only.")
        if spread and not assign_to:
            raise CommandError("--spread needs --assign-to (someone has to 'do' the steps).")
        if no_email:
            settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        staff = None
        if assign_to:
            staff = get_user_model().objects.filter(email__iexact=assign_to).first()
            if staff is None:
                raise CommandError(f"No user with email {assign_to}.")

        run = timezone.now().strftime("%H%M%S")  # keeps emails unique across runs
        tally = dict.fromkeys(STAGES, 0)

        for n in range(count):
            req = submit_consultation_request(fake_request(f"{run}{n}")).consultation_request
            if staff:
                assign_request(req, to=staff)

            stage = random.choice(STAGES) if spread else "new"
            if stage != "new":
                mark_fee_paid(
                    req, by=staff, amount=1000, currency="ZMW",
                    method=random.choice(["bank_transfer", "mobile_money"]),
                    reference=f"TEST-{run}{n}",
                )
            if stage in ("booked", "consulted"):
                book_consultation(
                    req, by=staff, location="Video call",
                    scheduled_for=timezone.now() + timedelta(days=random.randint(1, 14), hours=random.randint(0, 8)),
                )
            if stage == "consulted":
                save_consultation_notes(req, by=staff, notes="[Test] Warm, ready to proceed. Values family and faith.")
                mark_consulted(req, by=staff)
            tally[stage] += 1

        summary = ", ".join(f"{v} {k}" for k, v in tally.items() if v)
        self.stdout.write(self.style.SUCCESS(f"Created {count} test request(s): {summary}."))