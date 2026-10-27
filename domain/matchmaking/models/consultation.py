from django.conf import settings
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.consultation_request import ConsultationRequest


class Consultation(TimeStampedModel):

    class YesNo(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"

    class Readiness(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
    """
    What staff found at the consultation.
    The request itself stays exactly as the applicant submitted it.
    """
    request = models.OneToOneField(
        ConsultationRequest, on_delete=models.CASCADE, related_name="consultation"
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    location = models.CharField(
        max_length=200, blank=True,
        help_text="Where it will happen, e.g. Elyria office, video call, or an agreed venue.",
    )
    held_at = models.DateTimeField(null=True, blank=True)
    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_conducted",
    )
    notes = models.TextField("Matchmaker's overall notes & recommendation", blank=True)

    # ---------- Official Consultation Record
    recording_consent = models.CharField("Recording consent asked: client's response", max_length=3, choices=YesNo.choices, blank=True)
    identity_confirmed = models.CharField("Identity confirmed against enquiry form details", max_length=3, choices=YesNo.choices, blank=True)

    faith_matching = models.TextField("Does faith-based matching matter to you?", blank=True)
    hnw_discretion = models.TextField("Would you like the elevated discretion standard associated with the High-Net-Worth segment?", blank=True)

    a1 = models.TextField("Tell me about your last serious relationship — what worked, and what didn't?", blank=True)
    a2 = models.TextField("What have you learned about yourself since then?", blank=True)
    a3 = models.TextField("What does being “ready” for a relationship mean to you right now?", blank=True)
    a4 = models.TextField("Looking back, what's your honest read on what went wrong?", blank=True)
    a5 = models.TextField("How long has it been since that relationship ended, and how do you feel about it today?", blank=True)

    b1 = models.TextField("What does a shared life actually look like for you, day to day?", blank=True)
    b2 = models.TextField("What are three things you will not compromise on, and why?", blank=True)
    b3 = models.TextField("How central is faith, family, or career to how you want to live?", blank=True)
    b4 = models.TextField("Your partner is offered a great job elsewhere, and taking it means relocating. How should that decision be made?", blank=True)
    b5 = models.TextField("How do you imagine major financial decisions being made between you and a partner?", blank=True)
    b6 = models.TextField("How involved do you want extended family to be in daily life together?", blank=True)

    c1 = models.TextField("Describe the kind of person you're hoping to meet — not a checklist, but who they are.", blank=True)
    c2 = models.TextField("What's a quality you find yourself consistently drawn to, and why?", blank=True)

    d1 = models.TextField("How do you feel about receiving feedback or guidance during this process?", blank=True)

    e1 = models.TextField("Have any of your relationships ended on difficult terms recently?", blank=True)
    e2 = models.TextField("How do you typically handle rejection, or a lack of response from someone you're interested in?", blank=True)
    e3 = models.TextField("Your partner is clearly upset but says ‘nothing's wrong.’ What do you do?", blank=True)
    e4 = models.TextField("When you're upset, do you want to talk it through immediately, or do you need space first?", blank=True)

    f1 = models.TextField("What's something you're actively working on in yourself right now?", blank=True)
    f2 = models.TextField("What does a partner do that makes you feel truly supported, especially when things are hard?", blank=True)
    f3 = models.TextField("How easy or hard is it for you to let someone see you vulnerable?", blank=True)

    follow_up_questions = models.TextField("Other questions asked (follow-ups or new)", blank=True)

    readiness = models.CharField("Readiness score", max_length=10, choices=Readiness.choices, blank=True)
    readiness_set_at = models.DateTimeField(null=True, blank=True)
    readiness_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_scored",
    )

    # Locked = the fixed baseline. Never edited again.
    record_locked_at = models.DateTimeField(null=True, blank=True)
    record_locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_locked",
    )

    @property
    def is_locked(self):
        return self.record_locked_at is not None

    @property
    def answered_count(self):
        from domain.matchmaking.consultation_questions import QUESTION_FIELDS
        return sum(1 for f in QUESTION_FIELDS if (getattr(self, f) or "").strip())

    @property
    def question_count(self):
        from domain.matchmaking.consultation_questions import QUESTION_FIELDS
        return len(QUESTION_FIELDS)

    def __str__(self):
        return f"Consultation for {self.request.full_name}"