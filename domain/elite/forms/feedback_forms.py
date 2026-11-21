"""
The three Elite feedback forms, exactly as the client specified. The Case Handler asks these on a call
(or by message) and records the answers on the case; nothing is emailed. Every question is optional,
because people don't always answer everything.

Question types: rating (1-5), nps (0-10), choice (options), text (free text).
"""

RATING = "rating"
NPS = "nps"
CHOICE = "choice"
TEXT = "text"

YES_NO = [("yes", "Yes"), ("no", "No")]
YES_NO_LATER = [("yes", "Yes"), ("no", "No"), ("maybe_later", "Maybe later")]


def q(key, label, kind, options=None, required=False, show_if=None, default=None):
    return {"key": key, "label": label, "type": kind, "options": options or [], "required": required,
            "show_if": show_if, "default": default}


FORMS = {
    "A": [
        q("discreet", "How discreet did the process feel?", RATING),
        q("approach_respectful", "How respectful was the way the person was approached?", RATING),
        q("handler_clear", "How clear was communication from your Case Handler?", RATING),
        q("prepared", "How well were you prepared for the introduction?", RATING),
        q("expectations", "How did the Elite Grade experience compare with what you expected?", CHOICE,
          [("below", "Below"), ("as_expected", "As expected"), ("above", "Above")]),
        q("fee_worth", "Was the K35,000 fee worth it to you?", CHOICE, [("yes", "Yes"), ("partly", "Partly"), ("no", "No")]),
        q("worked_best", "What worked best?", TEXT, required=False),
        q("improve", "What should we improve?", TEXT, required=False),
        q("recommend_elite", "How likely are you to recommend Elite Grade to someone you trust?", NPS),
        q("recommend_elyria", "Would you be willing to recommend Elyria to someone you know?", CHOICE, YES_NO_LATER),
        q("referral_contact", "May we contact you about a referral?", CHOICE, YES_NO, show_if=("recommend_elyria", "yes")),
        q("testimonial", "May we use any of your comments as a testimonial?", CHOICE,
          [("no", "No"), ("anonymous", "Yes, anonymously"), ("named", "Yes, with my name")]),
        q("anything_else", "Anything else you want Elyria to know?", TEXT, required=False),
    ],
    "B": [
        q("comfortable", "How comfortable did you feel being approached?", RATING),
        q("first_contact_respectful", "How respectfully did Elyria handle the first contact?", RATING),
        q("acknowledgement_clear", "How clear was the Introduction Acknowledgement?", RATING),
        q("free_to_decline", "Did you feel free to decline at any point?", CHOICE, YES_NO),
        q("prepared", "How well were you prepared for the introduction?", RATING),
        q("intrusive", "Did anything about the process feel intrusive or uncomfortable?", CHOICE, YES_NO),
        q("intrusive_details", "What felt intrusive or uncomfortable?", TEXT, show_if=("intrusive", "yes")),
        q("open_to_joining", "Would you be open to joining Elyria in future?", CHOICE,
          [("yes", "Yes"), ("no", "No"), ("maybe", "Maybe")]),
        q("recommend_approach", "Would you recommend Elyria's approach to someone you trust?", CHOICE, YES_NO_LATER),
        q("contact_referral", "May we contact you about a referral or membership?", CHOICE, YES_NO),
        q("testimonial", "May we use any of your comments as a testimonial?", CHOICE,
          [("no", "No"), ("anonymous", "Yes, anonymously")]),
        q("anything_else", "Anything else you want Elyria to know?", TEXT, required=False),
    ],
    "C": [
        q("discreet", "How discreet did the process feel?", RATING),
        q("handler_clear", "How clear was communication from your Case Handler?", RATING),
        q("improve", "What should we improve?", TEXT, required=False),
        q("recommend_elyria", "Would you still recommend Elyria to someone you trust?", CHOICE, YES_NO_LATER),
    ],
}


TITLES = {
    "A": "Form A: the client, after the introduction",
    "B": "Form B: the named person, after the introduction",
    "C": "Form C: the client, closed without an introduction",
}


def for_display(form, answers):
    """Questions with their options as strings and the saved answer, ready for the case page."""
    out = []
    for question in FORMS[form]:
        kind = question["type"]
        if kind == RATING:
            choices = [(str(n), str(n)) for n in range(1, 6)]
        elif kind == NPS:
            choices = [(str(n), str(n)) for n in range(0, 11)]
        else:
            choices = question["options"]
        saved = answers.get(question["key"], "")
        out.append({**question, "choices": choices, "current": "" if saved == "" else str(saved)})
    return out


def _shown(question, data):
    if not question["show_if"]:
        return True
    key, value = question["show_if"]
    return data.get(key) == value


def clean_answers(form, data):
    """
    (answers, errors) from posted data. Unanswered questions are left out; a follow-up is dropped when its
    question isn't answered that way (e.g. intrusive details when they said No). errors: {key: message}.
    """
    answers, errors = {}, {}
    for question in FORMS[form]:
        key, kind = question["key"], question["type"]
        if not _shown(question, data):
            continue
        raw = (data.get(key) or "").strip()
        if not raw:
            if question["default"] is not None:
                answers[key] = question["default"]
            elif question["required"]:
                errors[key] = "Please answer this question."
            continue
        if kind in (RATING, NPS):
            top = 5 if kind == RATING else 10
            low = 1 if kind == RATING else 0
            if not raw.isdigit() or not low <= int(raw) <= top:
                errors[key] = f"Choose a number from {low} to {top}."
                continue
            answers[key] = int(raw)
        elif kind == CHOICE:
            if raw not in dict(question["options"]):
                errors[key] = "Choose one of the options."
                continue
            answers[key] = raw
        else:
            answers[key] = raw[:4000]
    return answers, errors


def red_flag_reasons(form, answers):
    """Any rating of 2 or below, 'Yes' to intrusive, or 'No' to free to decline."""
    reasons = []
    labels = {question["key"]: question["label"] for question in FORMS[form]}
    for question in FORMS[form]:
        value = answers.get(question["key"])
        if question["type"] == RATING and isinstance(value, int) and value <= 2:
            reasons.append(f"Rated {value}/5: {labels[question['key']]}")
    if answers.get("intrusive") == "yes":
        reasons.append("Said the process felt intrusive or uncomfortable")
    if answers.get("free_to_decline") == "no":
        reasons.append("Did not feel free to decline")
    return reasons


def is_referral_lead(form, answers):
    """A recommendation of 9-10 together with consent to be contacted (Form A)."""
    return (
        form == "A" and isinstance(answers.get("recommend_elite"), int) and answers["recommend_elite"] >= 9
        and answers.get("referral_contact") == "yes"
    )


def readable(form, answers):
    """[(label, answer as text)] in form order, for the case page."""
    rows = []
    for question in FORMS[form]:
        if question["key"] not in answers:
            continue
        value = answers[question["key"]]
        if question["type"] == CHOICE:
            value = dict(question["options"]).get(value, value)
        elif question["type"] == RATING:
            value = f"{value} / 5"
        elif question["type"] == NPS:
            value = f"{value} / 10"
        rows.append((question["label"], value))
    return rows