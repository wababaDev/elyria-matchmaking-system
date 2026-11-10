from django.urls import path

from domain.elite.views import public_views as public
from domain.elite.views import staff_views as staff

app_name = "elite"

urlpatterns = [
    # Website (E1)
    path("elite/apply/", public.ApplyView.as_view(), name="apply"),
    path("elite/apply/sent/", public.ApplySentView.as_view(), name="apply-sent"),
    path("elite/confirm/<str:token>/", public.ConfirmEmailView.as_view(), name="confirm"),

    # Staff: Admin sees every case, a Case Handler only hers
    path("management/elite/", staff.CaseListView.as_view(), name="cases"),
    path("management/elite/<int:pk>/", staff.CaseDetailView.as_view(), name="case-detail"),
    path("management/elite/<int:pk>/documents/upload/", staff.UploadDocumentView.as_view(), name="case-upload"),
    path("management/elite/<int:pk>/documents/received/", staff.DocumentsReceivedView.as_view(), name="case-received"),
    path("management/elite/<int:pk>/documents/<int:document_pk>/", staff.DocumentFileView.as_view(), name="case-document"),
    path("management/elite/<int:pk>/checks/", staff.SaveChecksView.as_view(), name="case-checks"),
    path("management/elite/<int:pk>/decide/", staff.DecideView.as_view(), name="case-decide"),

    # Part 2a (Case Handler; Admin can step in)
    path("management/elite/<int:pk>/handler/", staff.AssignHandlerView.as_view(), name="case-handler"),
    path("management/elite/<int:pk>/fee/", staff.RecordFeeView.as_view(), name="case-fee"),
    path("management/elite/<int:pk>/indemnity/", staff.IndemnityReceivedView.as_view(), name="case-indemnity"),
    path("management/elite/<int:pk>/person/", staff.RecordPersonView.as_view(), name="case-person"),
    path("management/elite/<int:pk>/outreach/", staff.RecordOutreachView.as_view(), name="case-outreach"),
    path("management/elite/<int:pk>/answer/", staff.RecordAnswerView.as_view(), name="case-answer"),
    path("management/elite/<int:pk>/acknowledgement/send/", staff.SendAcknowledgementView.as_view(), name="case-acknowledgement-send"),
    path("management/elite/<int:pk>/acknowledgement/", staff.RecordAcknowledgementView.as_view(), name="case-acknowledgement"),
    path("management/elite/<int:pk>/bronze/", staff.RecordBronzeAnswerView.as_view(), name="case-bronze"),
    path("management/elite/<int:pk>/reply-window/", staff.ExtendWindowView.as_view(), name="case-extend-window"),

    # Part 2b: the introduction, notes, deletion
    path("management/elite/<int:pk>/introduction/", staff.ScheduleIntroductionView.as_view(), name="case-introduction"),
    path("management/elite/<int:pk>/preparation/", staff.PreparationView.as_view(), name="case-preparation"),
    path("management/elite/<int:pk>/introduction/result/", staff.IntroResultView.as_view(), name="case-intro-result"),
    path("management/elite/<int:pk>/close/", staff.CloseCaseView.as_view(), name="case-close"),
    path("management/elite/<int:pk>/note/", staff.CaseNoteView.as_view(), name="case-note"),
    path("management/elite/<int:pk>/delete-now/", staff.DeleteNowView.as_view(), name="case-delete-now"),

     path("management/elite/<int:pk>/feedback/", staff.SaveFeedbackView.as_view(), name="case-feedback"),
]