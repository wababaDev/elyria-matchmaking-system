"""
The member's Self-Service Profile.

Fields, labels and options follow the approved prototype (member-profile.html) exactly.
Everything is blank-able so the member can save and return; what is required to
"Mark profile complete" lives in domain/matchmaking/profile_sections.py.
"""
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from domain.base.models import TimeStampedModel
from domain.matchmaking.models.client import Client
from domain.matchmaking.models.consultation_request import ConsultationRequest

TEXT = 300  # "A line or two for each"
SCALE_CHOICES = [(n, str(n)) for n in range(1, 6)]  # 1 = Not important … 5 = Essential


def text(label):
    return models.CharField(label, max_length=TEXT, blank=True)


def choice(label, choices, max_length=30):
    return models.CharField(label, max_length=max_length, choices=choices, blank=True)


def scale(label):
    return models.PositiveSmallIntegerField(label, choices=SCALE_CHOICES, null=True, blank=True)


def trait(label):
    return models.PositiveSmallIntegerField(
        label, null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )


class ClientProfile(TimeStampedModel):
    # ---------- Choices

    class RelationshipStatus(models.TextChoices):
        # Same values as the consultation request. Married/Separated were blocked there.
        SINGLE = "single", "Single"
        DIVORCED = "divorced", "Divorced"
        WIDOWED = "widowed", "Widowed"
        OTHER = "other", "Other"

    class Build(models.TextChoices):
        SLIM = "slim", "Slim"
        AVERAGE = "average", "Average"
        ATHLETIC = "athletic", "Athletic"
        CURVY = "curvy", "Curvy"
        BROAD = "broad", "Broad"

    class Education(models.TextChoices):
        SECONDARY = "secondary", "Secondary"
        DIPLOMA = "diploma", "Diploma / Certificate"
        BACHELORS = "bachelors", "Bachelor's degree"
        MASTERS = "masters", "Master's degree"
        DOCTORATE = "doctorate", "Doctorate"

    class LookingFor(models.TextChoices):
        FRIENDSHIP = "friendship", "Friendship"
        DATING = "dating", "Dating"
        LONG_TERM = "long_term", "Long-term relationship"
        MARRIAGE = "marriage", "Marriage"
        COMPANIONSHIP = "companionship", "Companionship"
        NOT_SURE = "not_sure", "Not sure yet"

    class MaritalHistory(models.TextChoices):
        NEVER = "never_married", "Never married"
        DIVORCED = "divorced", "Divorced"
        WIDOWED = "widowed", "Widowed"
        SEPARATED = "separated", "Separated"

    class YesNo(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"

    class WantChildren(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        OPEN = "open", "Open"
        UNSURE = "unsure", "Unsure"

    class LongestRelationship(models.TextChoices):
        UNDER_1 = "under_1y", "Under 1 year"
        Y1_3 = "1_3y", "1–3 years"
        Y3_5 = "3_5y", "3–5 years"
        Y5_10 = "5_10y", "5–10 years"
        OVER_10 = "over_10y", "Over 10 years"

    class TimeSince(models.TextChoices):
        UNDER_6M = "under_6m", "Under 6 months"
        M6_12 = "6_12m", "6–12 months"
        Y1_2 = "1_2y", "1–2 years"
        Y2_5 = "2_5y", "2–5 years"
        OVER_5 = "over_5y", "Over 5 years"

    class CoreValue(models.TextChoices):
        HONESTY = "honesty", "Honesty"
        FAITH = "faith", "Faith / Religion"
        FAMILY = "family", "Family"
        FINANCIAL = "financial_responsibility", "Financial Responsibility"
        AMBITION = "ambition", "Ambition"
        KINDNESS = "kindness", "Kindness"
        LOYALTY = "loyalty", "Loyalty"
        INDEPENDENCE = "independence", "Independence"
        COMMUNITY = "community", "Community Involvement"
        GROWTH = "personal_growth", "Personal Growth"

    class Religion(models.TextChoices):
        CATHOLIC = "catholic", "Christian – Catholic"
        PROTESTANT = "protestant", "Christian – Protestant"
        PENTECOSTAL = "pentecostal", "Christian – Pentecostal / Charismatic"
        ADVENTIST = "adventist", "Seventh-day Adventist"
        JEHOVAHS_WITNESS = "jehovahs_witness", "Jehovah's Witness"
        MUSLIM = "muslim", "Muslim"
        HINDU = "hindu", "Hindu"
        BAHAI = "bahai", "Bahá'í"
        JEWISH = "jewish", "Jewish"
        AFRICAN_TRADITIONAL = "african_traditional", "African Traditional Religion"
        OTHER = "other", "Other"
        SPIRITUAL = "spiritual", "Spiritual but not religious"
        NONE = "none", "No religious affiliation"
        PREFER_NOT = "prefer_not", "Prefer not to say"

    class Practice(models.TextChoices):
        VERY = "very_actively", "Very actively"
        ACTIVELY = "actively", "Actively"
        MODERATELY = "moderately", "Moderately"
        OCCASIONALLY = "occasionally", "Occasionally"
        RARELY = "rarely", "Rarely"
        CULTURALLY = "culturally", "Culturally only"
        NA = "not_applicable", "Not applicable"

    class FaithImportance(models.TextChoices):
        ESSENTIAL = "essential", "Essential"
        VERY = "very_important", "Very important"
        OPEN = "important_open", "Important but open"
        NOT_PARTICULARLY = "not_particularly", "Not particularly important"
        NOT_AT_ALL = "not_at_all", "Not important at all"

    class Saturday(models.TextChoices):
        HOME = "home", "Staying home"
        FAMILY = "family", "Visiting family"
        FRIENDS = "friends", "Going out with friends"
        OUTDOORS = "outdoors", "Outdoor activities"
        EXPLORING = "exploring", "Exploring somewhere new"
        PROJECTS = "projects", "Working on personal projects"
        MIXTURE = "mixture", "A mixture"

    class YesNoMaybe(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        MAYBE = "maybe", "Maybe"

    class YesNoOpen(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        OPEN = "open", "Open"

    class LongDistance(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        FOR_A_TIME = "for_a_time", "For a time"

    class Smoking(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        OCCASIONALLY = "occasionally", "Occasionally is fine"

    class Drinking(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        SOCIALLY = "socially", "Socially is fine"

    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="profile")

    # ---------- Confirm your details (pre-filled from the consultation request)
    full_name = models.CharField("Full name", max_length=150, blank=True)
    preferred_name = models.CharField("Preferred name", max_length=80, blank=True)
    age = models.PositiveSmallIntegerField(
        "Age", null=True, blank=True, validators=[MinValueValidator(20), MaxValueValidator(90)]
    )
    gender = choice("Gender", ConsultationRequest.Gender.choices)
    seeking = choice("Seeking", ConsultationRequest.Seeking.choices)
    relationship_status = choice("Relationship status", RelationshipStatus.choices)
    location = models.CharField("Location (country / city)", max_length=150, blank=True)
    nationality = models.CharField("Nationality", max_length=100, blank=True)
    occupation = models.CharField("Occupation / profession", max_length=150, blank=True)
    phone = models.CharField("Phone number", max_length=30, blank=True)

    # ---------- Additional personal information
    build = choice("General build", Build.choices)
    languages = models.CharField("Languages spoken", max_length=200, blank=True)
    education = choice("Education level", Education.choices)

    # ---------- Your personality (1 = left word, 5 = right word)
    trait_introvert_extrovert = trait("Introverted – Extroverted")
    trait_quiet_social = trait("Quiet – Social")
    trait_structured_spontaneous = trait("Structured – Spontaneous")
    trait_practical_creative = trait("Practical – Creative")
    trait_traditional_progressive = trait("Traditional – Progressive")

    # ---------- What are you looking for?
    looking_for = choice("What are you looking for?", LookingFor.choices)

    # ---------- Relationships & family
    marital_history = choice("Marital history", MaritalHistory.choices)
    previous_marriages = models.PositiveSmallIntegerField("Number of previous marriages", null=True, blank=True)
    has_children = choice("Do you have children?", YesNo.choices)
    children_count = models.PositiveSmallIntegerField(
        "How many?", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    children_ages = models.CharField("Ages", max_length=100, blank=True)
    children_living = models.CharField("Living arrangements", max_length=200, blank=True)
    wants_children = choice("Want children in future?", WantChildren.choices)
    longest_relationship = choice("Longest relationship", LongestRelationship.choices)
    time_since_last = choice("Time since last relationship ended", TimeSince.choices)

    # ---------- Your lifestyle
    social_life = text("Social life")
    travel = text("Travel")
    exercise = text("Exercise")
    food_preferences = text("Food preferences")
    entertainment = text("Entertainment")
    alcohol_smoking = text("Alcohol / smoking")
    pets = text("Pets")
    political_involvement = text("Political / social involvement")

    # ---------- Your core values
    core_values = models.JSONField("Your core values", default=list, blank=True)

    # ---------- Your faith
    religion = choice("Religious affiliation", Religion.choices)
    practice = choice("How actively you practise", Practice.choices)
    partner_faith_importance = choice("Importance of your partner sharing your faith", FaithImportance.choices)

    # ---------- Your family background
    parents_relationship = text("Relationship with parents")
    siblings = text("Number of siblings")
    family_structure = text("Family structure")
    family_closeness = text("Closeness to family")
    caring_for_parents = text("Expectations around caring for parents")
    extended_family_involvement = text("Desired extended-family involvement")
    cultural_traditions = text("Cultural traditions important to you")

    # ---------- Your daily life
    typical_weekday = text("Typical weekday")
    typical_weekend = text("Typical weekend")
    work_schedule = text("Work schedule")
    social_frequency = text("Social frequency")
    hobbies = text("Hobbies")
    interests = text("Interests")
    travel_habits = text("Travel habits")
    sleep_schedule = text("Sleep schedule")
    homebody_or_out = text("Homebody or going out?")
    cooking_or_eating_out = text("Cooking or eating out?")
    household_habits = text("Household habits")
    exercise_attitude = text("Attitude toward exercise")
    ideal_saturday = choice("My ideal Saturday is…", Saturday.choices)

    # ---------- Your finances (attitudes only, never income)
    employment_status = text("Employment status")
    financial_responsibilities = text("Financial responsibilities / dependants")
    saving_habits = text("Saving habits")
    spending_habits = text("Spending habits")
    debt_attitude = text("Attitude toward debt")
    financial_contribution = text("Expected financial contribution in a relationship")
    joint_or_separate = text("Joint or separate finances")
    housing_expectations = text("Housing expectations")
    extended_family_support = text("Willingness to support extended family")

    # ---------- Partner basics
    partner_gender = choice("Gender of preferred partner", ConsultationRequest.Gender.choices)
    partner_age_min = models.PositiveSmallIntegerField(
        "Age from", null=True, blank=True, validators=[MinValueValidator(20), MaxValueValidator(90)]
    )
    partner_age_max = models.PositiveSmallIntegerField(
        "Age to", null=True, blank=True, validators=[MinValueValidator(20), MaxValueValidator(90)]
    )
    partner_location = models.CharField("Preferred location", max_length=200, blank=True)
    willing_to_relocate = choice("Willing to relocate to your partner's location?", YesNoMaybe.choices)
    open_to_partner_children = choice("Open to a partner who already has children?", YesNoOpen.choices)
    open_to_long_distance = choice("Open to a long-distance relationship?", LongDistance.choices)
    relationship_structure = text("Preferred relationship structure / expectations")
    marriage_importance = scale("Importance of marriage")

    # ---------- Physical attraction
    attraction_importance = scale("Importance of physical attraction")
    partner_height = models.CharField("Height preference", max_length=100, blank=True)
    partner_build = choice("General build preference", Build.choices)

    # ---------- Partner values
    partner_values = models.JSONField("Partner values", default=list, blank=True)

    # ---------- Partner personality
    partner_trait_introvert_extrovert = trait("Introverted – Extroverted")
    partner_trait_quiet_social = trait("Quiet – Social")
    partner_trait_structured_spontaneous = trait("Structured – Spontaneous")
    partner_trait_practical_creative = trait("Practical – Creative")
    partner_trait_traditional_progressive = trait("Traditional – Progressive")

    # ---------- Partner lifestyle
    open_to_smoker = choice("Open to a partner who smokes?", Smoking.choices)
    open_to_drinker = choice("Open to a partner who drinks?", Drinking.choices)

    # ---------- Deal-breakers
    non_negotiables = models.JSONField("Non-negotiables", default=list, blank=True)  # max 5, checked in the form
    partner_preferences = models.TextField("Preferences", blank=True)
    affection_importance = scale("Importance of physical affection in a relationship")

    # ---------- State
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.client}"

    @property
    def is_complete(self):
        return self.completed_at is not None

    @property
    def core_values_display(self):
        return [self.CoreValue(v).label for v in self.core_values if v in self.CoreValue.values]

    @property
    def partner_values_display(self):
        return [self.CoreValue(v).label for v in self.partner_values if v in self.CoreValue.values]