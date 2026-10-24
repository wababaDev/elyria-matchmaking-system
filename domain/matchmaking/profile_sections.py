"""
The layout of the Self-Service Profile, in one place.

The member form, the progress bar, the "Mark profile complete" check and the staff
read-only view are all driven from SECTIONS, so they can never disagree.
Order, headings and hints follow the approved prototype (member-profile.html).
"""
from dataclasses import dataclass, field

# Widget kinds the portal template knows how to draw
INPUT = "input"        # text / number / email
SELECT = "select"
CHIPS = "chips"        # pick one, shown as pills
CHECKS = "checks"      # pick many, shown as pills
SCALE = "scale"        # 1–5 pills with "Not important … Essential"
SLIDER = "slider"      # 1–5 range between two words
TEXTAREA = "textarea"

TRAITS = [
    ("introvert_extrovert", "Introverted", "Extroverted"),
    ("quiet_social", "Quiet", "Social"),
    ("structured_spontaneous", "Structured", "Spontaneous"),
    ("practical_creative", "Practical", "Creative"),
    ("traditional_progressive", "Traditional", "Progressive"),
]

# Fields that only apply after a particular answer: {field: (depends on, value)}.
# They're hidden until then, and only required when they apply.
SHOW_WHEN = {
    "children_count": ("has_children", "yes"),
    "children_ages": ("has_children", "yes"),
    "children_living": ("has_children", "yes"),
    "education_other": ("education", "other"),
    "core_values_other": ("core_values", "other"),
    "ideal_saturday_other": ("ideal_saturday", "other"),
    "partner_values_other": ("partner_values", "other"),
}

# The prototype's "(optional)" fields, plus fields that can't be required yet
OPTIONAL = {
    "preferred_name",
    "political_involvement",
    "partner_height",
    "partner_build",
    "partner_preferences",
    "religion",  # Elyria's decision: always optional
}

# Placeholder text shown on a select before anything is chosen
SELECT_PLACEHOLDER = {"partner_build": "No preference"}


@dataclass
class Field:
    name: str
    kind: str = INPUT
    col: str = "col-md-6"
    hide_label: bool = False
    ends: tuple = ()          # sliders: ("Introverted", "Extroverted")
    placeholder: str = ""


@dataclass
class Section:
    id: str
    nav: str
    title: str
    hint: str = ""
    zone: str = ""            # "", "you" or "partner"
    fields: list = field(default_factory=list)
    has_photos: bool = False
    has_non_negotiables: bool = False


def _sliders(prefix):
    return [
        Field(f"{prefix}trait_{key}", SLIDER, col="col-12", ends=(left, right))
        for key, left, right in TRAITS
    ]


def _texts(names, col="col-md-6"):
    return [Field(n, INPUT, col=col) for n in names]


SECTIONS = [
    Section(
        "s-details", "Confirm your details", "Confirm your details",
        "These came from your consultation request. Correct anything that has changed.",
        fields=[
            Field("full_name"),
            Field("preferred_name"),
            Field("age", col="col-md-4"),
            Field("gender", SELECT, col="col-md-4"),
            Field("seeking", SELECT, col="col-md-4"),
            Field("relationship_status", SELECT),
            Field("location"),
            Field("nationality"),
            Field("occupation"),
            Field("phone"),
        ],
    ),
    # ---------------- About You
    Section(
        "s-personal", "Personal information", "Additional personal information", "A little more about you.",
        zone="you", has_photos=True,
        fields=[
            Field("build", SELECT, col="col-md-4"),
            Field("languages", col="col-md-4", placeholder="e.g. English, Bemba"),
            Field("education", SELECT, col="col-md-4"),
            Field("education_other", col="col-md-4 offset-md-8", placeholder="Please specify"),
        ],
    ),
    Section(
        "s-personality", "Your personality", "Your personality", "Move each slider to where you naturally sit.",
        zone="you", fields=_sliders(""),
    ),
    Section(
        "s-looking", "What you're looking for", "What are you looking for?", "Choose one.",
        zone="you", fields=[Field("looking_for", CHIPS, col="col-12", hide_label=True)],
    ),
    Section(
        "s-family-status", "Relationships & family", "Relationships & family",
        "Facts only. The story behind them is for your conversations with your matchmaker.",
        zone="you",
        fields=[
            Field("marital_history", SELECT),
            Field("previous_marriages"),
            Field("has_children", CHIPS, col="col-12"),
            Field("children_count", col="col-md-3"),
            Field("children_ages", col="col-md-4", placeholder="e.g. 6, 9"),
            Field("children_living", col="col-md-5", placeholder="e.g. live with me"),
            Field("wants_children", SELECT, col="col-md-4"),
            Field("longest_relationship", SELECT, col="col-md-4"),
            Field("time_since_last", SELECT, col="col-md-4"),
        ],
    ),
    Section(
        "s-lifestyle", "Your lifestyle", "Your lifestyle", "A line or two for each.", zone="you",
        fields=_texts([
            "social_life", "travel", "exercise", "food_preferences",
            "entertainment", "alcohol_smoking", "pets", "political_involvement",
        ]),
    ),
    Section(
        "s-values", "Your core values", "Your core values", "Select all that apply.", zone="you",
        fields=[
            Field("core_values", CHECKS, col="col-12", hide_label=True),
            Field("core_values_other", placeholder="Please specify"),
        ],
    ),
    Section(
        "s-faith", "Your faith", "Your faith", zone="you",
        fields=[
            Field("religion", SELECT),
            Field("practice", SELECT),
            Field("partner_faith_importance", SELECT, col="col-md-12"),
        ],
    ),
    Section(
        "s-background", "Family background", "Your family background", zone="you",
        fields=_texts([
            "parents_relationship", "siblings", "family_closeness",
            "caring_for_parents", "extended_family_involvement", "cultural_traditions",
        ]),
    ),
    Section(
        "s-daily", "Your daily life", "Your daily life", zone="you",
        fields=_texts([
            "typical_weekday", "typical_weekend", "work_schedule", "social_frequency",
            "hobbies", "interests", "travel_habits", "sleep_schedule",
            "homebody_or_out", "cooking_or_eating_out",
        ]) + [
            Field("ideal_saturday", CHIPS, col="col-12"),
            Field("ideal_saturday_other", placeholder="Please specify"),
        ],
    ),
    Section(
        "s-finances", "Your finances", "Your finances",
        "Attitudes and expectations only. We'll never ask for income here.", zone="you",
        fields=_texts([
            "employment_status", "financial_responsibilities", "saving_habits", "spending_habits",
            "debt_attitude", "financial_contribution", "joint_or_separate",
            "housing_expectations", "extended_family_support",
        ]),
    ),
    # ---------------- About Your Ideal Partner
    Section(
        "p-basics", "Partner basics", "Partner basics", zone="partner",
        fields=[
            Field("partner_gender", SELECT, col="col-md-4"),
            Field("partner_age_min", col="col-md-4"),
            Field("partner_age_max", col="col-md-4"),
            Field("partner_location", placeholder="e.g. Lusaka, or anywhere in Zambia"),
            Field("willing_to_relocate", SELECT),
            Field("open_to_partner_children", SELECT),
            Field("open_to_long_distance", SELECT),
            Field("relationship_structure", col="col-12"),
            Field("marriage_importance", SCALE, col="col-12"),
        ],
    ),
    Section(
        "p-attraction", "Physical attraction", "Physical attraction", zone="partner",
        fields=[
            Field("attraction_importance", SCALE, col="col-12"),
            Field("partner_height"),
            Field("partner_build", SELECT),
        ],
    ),
    Section(
        "p-values", "Partner values", "Partner values", "Select all that matter in a partner.", zone="partner",
        fields=[
            Field("partner_values", CHECKS, col="col-12", hide_label=True),
            Field("partner_values_other", placeholder="Please specify"),
        ],
    ),
    Section(
        "p-personality", "Partner personality", "Partner personality", "Where would your ideal partner sit?",
        zone="partner", fields=_sliders("partner_"),
    ),
    Section(
        "p-lifestyle", "Partner lifestyle", "Partner lifestyle", zone="partner",
        fields=[Field("open_to_smoker", SELECT), Field("open_to_drinker", SELECT)],
    ),
    Section(
        "p-dealbreakers", "Deal-breakers", "Deal-breakers", zone="partner", has_non_negotiables=True,
        fields=[
            Field("partner_preferences", TEXTAREA, col="col-12"),
            Field("affection_importance", SCALE, col="col-12"),
        ],
    ),
]

FIELD_NAMES = [f.name for s in SECTIONS for f in s.fields]
FIELDS_BY_NAME = {f.name: f for s in SECTIONS for f in s.fields}


def is_filled(value):
    return value not in (None, "", [], ())


def is_required(name, profile):
    if name in OPTIONAL:
        return False
    if name in SHOW_WHEN:
        return applies(name, profile)
    return True


def applies(name, profile):
    """True unless the field depends on an answer the member didn't give."""
    if name not in SHOW_WHEN:
        return True
    depends_on, value = SHOW_WHEN[name]
    answer = getattr(profile, depends_on)
    return value in answer if isinstance(answer, list) else answer == value


def missing_in_section(section, profile, *, has_photos):
    """Labels of the required answers still empty in one section."""
    model = type(profile)
    missing = [
        str(model._meta.get_field(f.name).verbose_name)
        for f in section.fields
        if is_required(f.name, profile) and not is_filled(getattr(profile, f.name))
    ]
    if section.has_photos and not has_photos:
        missing.append("At least one profile photo")
    return missing


def section_status(profile, *, has_photos):
    """[(section, [missing labels]), ...] in page order."""
    return [(s, missing_in_section(s, profile, has_photos=has_photos)) for s in SECTIONS]


def _display(profile, spec):
    model_field = type(profile)._meta.get_field(spec.name)
    value = getattr(profile, spec.name)
    if not is_filled(value):
        return ""
    if spec.kind == CHECKS:
        labels = dict(type(profile).CoreValue.choices)
        return ", ".join(str(labels.get(v, v)) for v in value)
    if spec.kind in (SLIDER, SCALE):
        return f"{value} of 5"
    if model_field.choices:
        return str(dict(model_field.flatchoices).get(value, value))
    return str(value)


def answers(profile):
    """For staff: [(section, [(label, answer), ...]), ...] in page order. Empty answers show as ''."""
    model = type(profile)
    result = []
    for section in SECTIONS:
        rows = [
            (str(model._meta.get_field(f.name).verbose_name), _display(profile, f))
            for f in section.fields
            if applies(f.name, profile)  # e.g. no "Education (other)" row unless they chose Other
        ]
        if section.has_non_negotiables:
            rows.insert(0, ("Non-negotiables", "; ".join(profile.non_negotiables)))
        result.append((section, rows))
    return result


def missing_field_names(profile):
    """Names of required fields that are still empty (for highlighting them on the page)."""
    return {
        f.name
        for s in SECTIONS
        for f in s.fields
        if is_required(f.name, profile) and not is_filled(getattr(profile, f.name))
    }


STAFF_GROUPS = [
    ("", "Their details"),
    ("you", "About them"),
    ("partner", "Their ideal partner"),
]


def answers_by_group(profile, *, has_photos):
    """
    For the staff member page: sections numbered 1..n like the member sees them,
    grouped into details / about them / ideal partner, with a count of missing answers.
    """
    rows_by_id = {s.id: rows for s, rows in answers(profile)}
    missing_by_id = {s.id: missing for s, missing in section_status(profile, has_photos=has_photos)}
    groups, number = [], 0
    for zone, label in STAFF_GROUPS:
        sections = []
        for section in (s for s in SECTIONS if s.zone == zone):
            number += 1
            sections.append({
                "section": section,
                "number": number,
                "rows": rows_by_id[section.id],
                "missing": len(missing_by_id[section.id]),
            })
        groups.append({"zone": zone, "label": label, "sections": sections})
    return groups