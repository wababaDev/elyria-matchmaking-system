from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from domain.base.models import TimeStampedModel

MIN_AGE = 20
MAX_AGE = 90

# TODO: confirm exact wording with Elyria (Open Questions #2)
NOT_ELIGIBLE_MESSAGE = (
    "Thank you for your interest. Elyria works only with clients who are not currently "
    "married or separated, so we're unable to proceed with your request at this time."
)


class ConsultationRequestQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=ConsultationRequest.OPEN_STATUSES)


class ConsultationRequest(TimeStampedModel):
    class Gender(models.TextChoices):
        # TODO: confirm options with Elyria (Open Questions #1)
        FEMALE = "female", "Female"
        MALE = "male", "Male"

    class Seeking(models.TextChoices):
        # TODO: confirm options with Elyria (Open Questions #1)
        MAN = "man", "A man"
        WOMAN = "woman", "A woman"

    class RelationshipStatus(models.TextChoices):
        SINGLE = "single", "Single (never married)"
        DIVORCED = "divorced", "Divorced"
        WIDOWED = "widowed", "Widowed"
        SEPARATED = "separated", "Separated"
        MARRIED = "married", "Married"

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        FEE_PAID = "fee_paid", "Fee paid"
        CONSULTED = "consulted", "Consulted"
        BECAME_MEMBER = "became_member", "Became member"
        DECLINED = "declined", "Declined"
        CLOSED = "closed", "Closed"


    class Currency(models.TextChoices):
        ZMW = "ZMW", "ZMW (Kwacha)"
        USD = "USD", "USD"

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        MOBILE_MONEY = "mobile_money", "Mobile money"
        CASH = "cash", "Cash"
        OTHER = "other", "Other"

    BLOCKED_STATUSES = [RelationshipStatus.MARRIED, RelationshipStatus.SEPARATED]
    OPEN_STATUSES = [Status.AWAITING_PAYMENT, Status.FEE_PAID, Status.CONSULTED]

    # --- From the public form ---
    full_name = models.CharField(max_length=150)
    preferred_name = models.CharField(max_length=80)
    gender = models.CharField(max_length=20, choices=Gender.choices)
    age = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(MIN_AGE, message=f"You must be at least {MIN_AGE} to apply."),
            MaxValueValidator(MAX_AGE, message=f"Please enter an age of {MAX_AGE} or under."),
        ]
    )
    seeking = models.CharField(max_length=20, choices=Seeking.choices)
    relationship_status = models.CharField(max_length=20, choices=RelationshipStatus.choices)
    location = models.CharField("Location (country / city)", max_length=150)
    nationality = models.CharField(max_length=100)
    occupation = models.CharField("Occupation / profession", max_length=150)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=30)

    # --- Staff tracking ---
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT, db_index=True
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_consultation_requests",
    )
    resubmission_count = models.PositiveIntegerField(
        default=0, help_text="Times the same email submitted again while this request was open."
    )
    last_resubmitted_at = models.DateTimeField(null=True, blank=True)
    fee_paid_at = models.DateTimeField(null=True, blank=True)
    fee_marked_paid_by = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name="+",
        )

    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fee_currency = models.CharField(max_length=3, choices=Currency.choices, blank=True)
    fee_payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    fee_reference = models.CharField(max_length=100, blank=True, help_text="Bank or mobile money reference.")

    objects = ConsultationRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES