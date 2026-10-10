from django.db import models

from domain.base.models import TimeStampedModel


class SiteSettings(TimeStampedModel):
    """One row only (pk=1). Edited by Admin under Settings → General."""
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=1000)
    consultation_fee_currency = models.CharField(max_length=3, default="ZMW")
    bank_details = models.TextField(blank=True, help_text="Shown in the payment email. Bank, account name, number, branch.")
    mobile_money_details = models.TextField(blank=True, help_text="Shown in the payment email. Network, name, number.")
    default_consultation_location = models.CharField(
        max_length=200, blank=True, help_text="Pre-filled when booking a consultation, e.g. the office address."
    )
    contact_phone = models.CharField(max_length=30, blank=True, default="+260 779 127 695")
    contact_email = models.EmailField(blank=True, default="info@elyriamatchmaking.com")
    business_address = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def fee_display(self):
        if self.consultation_fee_currency == "ZMW":
            return f"K{self.consultation_fee:,.0f}"
        return f"{self.consultation_fee_currency} {self.consultation_fee:,.2f}"

    @property
    def payment_details_ready(self):
        return bool(self.bank_details.strip() or self.mobile_money_details.strip())