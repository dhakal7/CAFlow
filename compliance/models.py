from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class ComplianceDeadline(FirmAwareModel):
    """
    Tracks statutory tax, audit, and legal compliance deadlines according to Nepal Acts.
    """
    class GoverningAct(models.TextChoices):
        INCOME_TAX = 'INCOME_TAX', _('Income Tax Act, 2058')
        VAT = 'VAT', _('Value Added Tax (VAT) Act, 2052')
        COMPANIES_ACT = 'COMPANIES_ACT', _('Companies Act, 2063')
        ICAN_ACT = 'ICAN_ACT', _('Nepal Chartered Accountants Act, 2053')
        LABOUR_ACT = 'LABOUR_ACT', _('Labour Act & SSF Rules, 2074')
        OTHER = 'OTHER', _('Other Statutory Body')

    class Status(models.TextChoices):
        UPCOMING = 'UPCOMING', _('Upcoming')
        IN_PROGRESS = 'IN_PROGRESS', _('In Preparation')
        FILED = 'FILED', _('Filed & Verified')
        OVERDUE = 'OVERDUE', _('Overdue / Penalty Risk')

    title = models.CharField(_('Compliance Filing Title'), max_length=255)
    governing_act = models.CharField(
        _('Governing Act / Authority'),
        max_length=40,
        choices=GoverningAct.choices,
        default=GoverningAct.INCOME_TAX,
    )
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='compliance_deadlines',
        null=True,
        blank=True,
        verbose_name=_('Client Entity (or General Firm Deadline)'),
    )
    due_date_bs = models.CharField(
        _('Due Date (Bikram Sambat)'),
        max_length=20,
        help_text=_('e.g. 2081-06-25'),
    )
    due_date_ad = models.DateField(_('Due Date (Gregorian / A.D.)'))
    status = models.CharField(
        _('Filing Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.UPCOMING,
    )
    notes = models.TextField(_('Statutory Notes / Penalty Guidelines'), blank=True)
    assigned_to = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_compliance',
    )

    class Meta:
        verbose_name = _('Compliance Deadline')
        verbose_name_plural = _('Compliance Deadlines')
        ordering = ['due_date_ad']

    def __str__(self):
        return f"{self.title} - BS {self.due_date_bs}"
