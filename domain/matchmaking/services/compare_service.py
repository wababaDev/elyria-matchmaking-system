"""
Consultation vs profile: the questions a member is asked twice, side by side.

The system only flags hard facts (age, gender, seeking, relationship status).
Open answers are shown next to each other for the matchmaker to judge; the system
never decides whether those differ.
"""
from domain.matchmaking.profile_sections import FIELDS_BY_NAME, display_value

# Each row: what to show from the request (R) or the consultation record (C), and from the profile (P).
COMPARISONS = [
    {"key": "age", "title": "Age", "consultation": [("R", "age")], "profile": ["age"], "fact": True},
    {"key": "gender", "title": "Gender", "consultation": [("R", "gender")], "profile": ["gender"], "fact": True},
    {"key": "seeking", "title": "Who they are seeking", "consultation": [("R", "seeking")], "profile": ["seeking"], "fact": True},
    {"key": "status", "title": "Relationship status", "consultation": [("R", "relationship_status")],
     "profile": ["relationship_status"], "fact": True},
    {"key": "a1", "title": "Last serious relationship", "consultation": [("C", "a1")],
     "profile": ["marital_history", "previous_marriages", "longest_relationship"]},
    {"key": "a5", "title": "Time since the relationship ended", "consultation": [("C", "a5")],
     "profile": ["time_since_last"]},
    {"key": "b2", "title": "Non-negotiables", "consultation": [("C", "b2")], "profile": ["non_negotiables"]},
    {"key": "b3", "title": "Faith, family and career", "consultation": [("C", "b3")],
     "profile": ["religion", "practice", "partner_faith_importance", "family_closeness"]},
    {"key": "b4", "title": "Relocating for a partner's job", "consultation": [("C", "b4")],
     "profile": ["willing_to_relocate"]},
    {"key": "b5", "title": "Financial decisions", "consultation": [("C", "b5")],
     "profile": ["joint_or_separate", "financial_contribution"]},
    {"key": "b6", "title": "Extended family involvement", "consultation": [("C", "b6")],
     "profile": ["extended_family_involvement"]},
]

AGE_TOLERANCE = 1  # a birthday between the request and the profile is not a discrepancy


def _request_value(cr, field):
    display = getattr(cr, f"get_{field}_display", None)
    value = display() if display else getattr(cr, field)
    return "" if value is None else str(value)


def _profile_value(profile, field):
    if field == "non_negotiables":
        return "; ".join(profile.non_negotiables or [])
    return display_value(profile, FIELDS_BY_NAME[field])


def _label(model, field):
    return str(model._meta.get_field(field).verbose_name)


def _differs(row, cr, profile):
    """Only for hard facts. Compares raw values, so wording can't cause a false alarm."""
    field = row["profile"][0]
    asked = getattr(cr, row["consultation"][0][1])
    answered = getattr(profile, field)
    if asked in (None, "") or answered in (None, ""):
        return False
    if field == "age":
        return abs(int(asked) - int(answered)) > AGE_TOLERANCE
    return str(asked) != str(answered)


def compare(client):
    """Rows for the compare table, or [] if there is no record or profile to compare yet."""
    cr = client.consultation_request
    consultation = getattr(cr, "consultation", None)
    profile = getattr(client, "profile", None)
    if not profile:
        return []

    rows = []
    for row in COMPARISONS:
        left = []
        for source, field in row["consultation"]:
            if source == "R":
                left.append(("Request", _request_value(cr, field)))
            elif consultation:
                left.append((field.upper(), (getattr(consultation, field) or "").strip()))
        right = [(_label(type(profile), f), _profile_value(profile, f)) for f in row["profile"]]

        rows.append({
            "key": row["key"],
            "title": row["title"],
            "fact": row.get("fact", False),
            "consultation": left,
            "profile": right,
            "differs": row.get("fact", False) and _differs(row, cr, profile),
            # Plain text used to pre-fill "Log discrepancy"
            "consultation_text": "\n".join(v for _, v in left if v),
            "profile_text": "\n".join(f"{label}: {v}" for label, v in right if v),
        })
    return rows