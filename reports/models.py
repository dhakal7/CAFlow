from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class SavedReportConfig(FirmAwareModel):
    """
    Stores saved custom filter criteria for reports (TDS reconciliation, VAT register, client billing summaries).
    """
    title = models.CharField(_('Report Name'), max_length=255)
    report_type = models.CharField(_('Report Type'), max_length=100)
    parameters_json = models.JSONField(_('Filter Parameters'), default=dict, blank=True)

    class Meta:
        verbose_name = _('Saved Report Configuration')
        verbose_name_plural = _('Saved Report Configurations')

    def __str__(self):
        return self.title
