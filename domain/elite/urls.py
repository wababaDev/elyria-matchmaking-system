from django.urls import path

from domain.elite.views import public_views as public
from domain.elite.views import staff_views as staff

app_name = "elite"

urlpatterns = [
    # Website (E1)
    path("elite/apply/", public.ApplyView.as_view(), name="apply"),
    path("elite/apply/sent/", public.ApplySentView.as_view(), name="apply-sent"),
    path("elite/confirm/<str:token>/", public.ConfirmEmailView.as_view(), name="confirm"),

    # Staff (Admin only)
    path("management/elite/", staff.CaseListView.as_view(), name="cases"),
    path("management/elite/<int:pk>/", staff.CaseDetailView.as_view(), name="case-detail"),
    path("management/elite/<int:pk>/documents/upload/", staff.UploadDocumentView.as_view(), name="case-upload"),
    path("management/elite/<int:pk>/documents/received/", staff.DocumentsReceivedView.as_view(), name="case-received"),
    path("management/elite/<int:pk>/documents/<int:document_pk>/", staff.DocumentFileView.as_view(), name="case-document"),
    path("management/elite/<int:pk>/checks/", staff.SaveChecksView.as_view(), name="case-checks"),
    path("management/elite/<int:pk>/decide/", staff.DecideView.as_view(), name="case-decide"),
]