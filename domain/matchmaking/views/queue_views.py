from django.views.generic import TemplateView

from domain.base.mixins import StaffRequiredMixin
from domain.matchmaking.services.queue_service import queue_for


class MyQueueView(StaffRequiredMixin, TemplateView):
    template_name = "domain/management/queue.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = queue_for(self.request.user)
        current = self.request.GET.get("tab", "all")

        # Each row carries its own "next step" so the All tab still makes sense
        rows = [
            {"item": item, "next_step": section["next_step"]}
            for section in sections
            if current in ("all", section["key"])
            for item in section["items"]
        ]

        context.update(
            sections=sections,
            current_tab=current,
            total=sum(len(s["items"]) for s in sections),
            rows=rows,
        )
        return context