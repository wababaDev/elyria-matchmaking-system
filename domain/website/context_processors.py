from domain.matchmaking.forms import ConsultationRequestForm
from domain.matchmaking.models import ConsultationRequest
from domain.matchmaking.models.consultation_request import NOT_ELIGIBLE_MESSAGE

from domain.website.models import SiteSettings

def consultation_form(request):
    return {
        "consultation_form": ConsultationRequestForm(),
        "consultation_blocked_statuses": ",".join(ConsultationRequest.BLOCKED_STATUSES),
        "consultation_not_eligible_message": NOT_ELIGIBLE_MESSAGE,
    }

def site_settings(request):
    return {"site": SiteSettings.load()}