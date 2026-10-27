"""
The Official Consultation Record, laid out once.

The question wording lives on the Consultation model (each field's verbose_name),
so this file only says which fields go in which section, in the order of Elyria's form.
"""

SECTIONS = [
    {
        "code": "",
        "title": "Segment Placement Questions",
        "hint": "Asked of every client, regardless of segment.",
        "fields": ["faith_matching", "hnw_discretion"],
    },
    {"code": "A", "title": "Relationship History & Readiness", "fields": ["a1", "a2", "a3", "a4", "a5"]},
    {"code": "B", "title": "Values & Life Vision", "fields": ["b1", "b2", "b3", "b4", "b5", "b6"]},
    {"code": "C", "title": "What They're Seeking", "fields": ["c1", "c2"]},
    {"code": "D", "title": "Engagement & Process Fit", "fields": ["d1"]},
    {"code": "E", "title": "Boundary & Ethics Probing", "fields": ["e1", "e2", "e3", "e4"]},
    {"code": "F", "title": "Emotional Self-Awareness", "fields": ["f1", "f2", "f3"]},
    {
        "code": "",
        "title": "Other Questions Asked by Matchmaker",
        "hint": "Follow-ups or new questions.",
        "fields": ["followk_up_questions"],
        "side": True,
    },
    {
        "code": "",
        "title": "Matchmaker's Overall Notes & Recommendation",
        "hint": "Include the recommended tier, if discussed.",
        "fields": ["notes"],
        "side": True,
    },
]

# The interview questions (segment placement + A to F): used for "x of y answered"
QUESTION_FIELDS = [f for s in SECTIONS if not s.get("side") for f in s["fields"]]

# Every text box on the record, including the matchmaker's own boxes
TEXT_FIELDS = [f for s in SECTIONS for f in s["fields"]]

BEFORE_YOU_BEGIN = ["recording_consent", "identity_confirmed"]

# What must be filled in before the record can be locked
REQUIRED_TO_LOCK = ["recording_consent", "identity_confirmed", "notes"]