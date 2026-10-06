from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class ComplianceType(FirmAwareModel):
    """
    Configurable Compliance Filing Types for CA firms.
    Allows firms to customize VAT, TDS, Income Tax, OCR, SSF, and Audit schedules.
    """
    class Category(models.TextChoices):
        VAT = 'VAT', _('Value Added Tax (VAT) Act, 2052')
        TDS = 'TDS', _('Withholding Tax (TDS) / E-TDS')
        INCOME_TAX = 'INCOME_TAX', _('Income Tax Act, 2058')
        COMPANIES_ACT = 'COMPANIES_ACT', _('Companies Act, 2063 (OCR)')
        ICAN_ACT = 'ICAN_ACT', _('ICAN Audit Guidelines & Standards')
        LABOUR_ACT = 'LABOUR_ACT', _('Labour Act & SSF Rules, 2074')
        OTHER = 'OTHER', _('Other Statutory Authority')

    class Frequency(models.TextChoices):
        NONE = 'NONE', _('One-off / Ad-hoc')
        MONTHLY = 'MONTHLY', _('Monthly')
        QUARTERLY = 'QUARTERLY', _('Quarterly')
        TRIANNUAL = 'TRIANNUAL', _('Every 4 Months (Trimester)')
        BIANNUAL = 'BIANNUAL', _('Semi-Annually / Bi-Annual')
        ANNUAL = 'ANNUAL', _('Annually')

    name = models.CharField(_('Compliance Type Name'), max_length=255)
    code = models.CharField(_('Code / Identifier'), max_length=50, blank=True)
    category = models.CharField(
        _('Governing Category / Act'),
        max_length=40,
        choices=Category.choices,
        default=Category.VAT,
    )
    statutory_authority = models.CharField(
        _('Statutory Authority / Portal'),
        max_length=150,
        blank=True,
        help_text=_('e.g. Inland Revenue Department (IRD), Office of Company Registrar (OCR), SSF'),
    )
    frequency = models.CharField(
        _('Default Frequency'),
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.MONTHLY,
    )
    default_priority = models.CharField(
        _('Default Priority'),
        max_length=20,
        choices=[
            ('LOW', _('Low')),
            ('MEDIUM', _('Medium')),
            ('HIGH', _('High')),
            ('URGENT', _('Urgent')),
        ],
        default='MEDIUM',
    )
    due_day_bs = models.PositiveSmallIntegerField(
        _('Default Due Day (Bikram Sambat)'),
        null=True,
        blank=True,
        help_text=_('e.g. 25 for 25th of month (VAT/TDS), or 30 for month-end'),
    )
    description = models.TextField(_('Description & Statutory Rules'), blank=True)
    penalty_guidelines = models.TextField(_('Statutory Penalty Guidelines'), blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)
    is_system_default = models.BooleanField(_('System Template'), default=False)

    class Meta:
        verbose_name = _('Compliance Type')
        verbose_name_plural = _('Compliance Types')
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class ClientComplianceRequirement(FirmAwareModel):
    """
    Subscribed compliance obligations for a specific client entity.
    Accommodates rule: 'Do not assume every client has every compliance requirement.'
    """
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='compliance_requirements',
    )
    compliance_type = models.ForeignKey(
        ComplianceType,
        on_delete=models.CASCADE,
        related_name='client_requirements',
    )
    frequency = models.CharField(
        _('Client Filing Frequency'),
        max_length=20,
        choices=ComplianceType.Frequency.choices,
        default=ComplianceType.Frequency.MONTHLY,
    )
    assigned_staff = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_client_compliance_requirements',
    )
    reviewer = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_client_compliance_requirements',
    )
    notes = models.TextField(_('Client-specific Filing Notes'), blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        verbose_name = _('Client Compliance Requirement')
        verbose_name_plural = _('Client Compliance Requirements')
        unique_together = ('client', 'compliance_type')

    def __str__(self):
        return f"{self.client.name} - {self.compliance_type.name}"

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValidationError({'client': _('Client must belong to the same firm as the requirement.')})
        if self.compliance_type_id and self.firm_id and self.compliance_type.firm_id != self.firm_id:
            raise ValidationError({'compliance_type': _('Compliance type must belong to the same firm.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm.'))
        if self.compliance_type_id and self.firm_id and self.compliance_type.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a compliance type from another firm.'))
        super().save(*args, **kwargs)


class ComplianceDeadline(FirmAwareModel):
    """
    Tracks statutory tax, audit, and legal compliance deadlines according to Nepal Acts.
    Supports complete CA workflow: Deadline -> Preparation -> Documents -> Review -> Filing -> Completed.
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
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        WAITING_FOR_CLIENT = 'WAITING_FOR_CLIENT', _('Waiting for Client')
        READY_FOR_REVIEW = 'READY_FOR_REVIEW', _('Ready for Review')
        FILED = 'FILED', _('Filed')
        COMPLETED = 'COMPLETED', _('Completed')
        OVERDUE = 'OVERDUE', _('Overdue')
        CANCELLED = 'CANCELLED', _('Cancelled')
        # Backward compatibility alias
        DUE_SOON = 'DUE_SOON', _('Due Soon')

    class Priority(models.TextChoices):
        LOW = 'LOW', _('Low')
        MEDIUM = 'MEDIUM', _('Medium')
        HIGH = 'HIGH', _('High')
        URGENT = 'URGENT', _('Urgent')

    class RecurrenceFrequency(models.TextChoices):
        NONE = 'NONE', _('None (One-off)')
        MONTHLY = 'MONTHLY', _('Monthly')
        QUARTERLY = 'QUARTERLY', _('Quarterly')
        TRIANNUAL = 'TRIANNUAL', _('Every 4 Months')
        BIANNUAL = 'BIANNUAL', _('Semi-Annually')
        ANNUAL = 'ANNUAL', _('Annually')

    title = models.CharField(_('Compliance Filing Title'), max_length=255)
    compliance_type = models.ForeignKey(
        ComplianceType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deadlines',
        verbose_name=_('Configurable Compliance Type'),
    )
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
    description = models.TextField(_('Filing Description & Scope'), blank=True)
    period = models.CharField(
        _('Period / Return Cycle'),
        max_length=100,
        blank=True,
        help_text=_('e.g. Bhadra 2081, Q1 2081/82, Ashoj 2081'),
    )
    due_date_bs = models.CharField(
        _('Due Date (Bikram Sambat)'),
        max_length=20,
        help_text=_('e.g. 2081-06-25'),
    )
    due_date_ad = models.DateField(_('Due Date (Gregorian / A.D.)'))
    assigned_to = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_compliance',
        verbose_name=_('Assigned Staff'),
    )
    reviewer = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_compliance',
        verbose_name=_('Reviewer / Partner'),
    )
    status = models.CharField(
        _('Filing Status'),
        max_length=25,
        choices=Status.choices,
        default=Status.UPCOMING,
        db_index=True,
    )
    priority = models.CharField(
        _('Priority'),
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
    )
    notes = models.TextField(_('Statutory Notes / Penalty Guidelines'), blank=True)
    completion_date = models.DateField(_('Completion Date'), null=True, blank=True)
    filing_reference_number = models.CharField(
        _('Filing / Reference / Ack No.'),
        max_length=100,
        blank=True,
        help_text=_('IRD Token / SSF Receipt / OCR Verification No.'),
    )

    # Recurring configuration
    is_recurring = models.BooleanField(_('Is Recurring'), default=False)
    recurrence_frequency = models.CharField(
        _('Recurrence Frequency'),
        max_length=20,
        choices=RecurrenceFrequency.choices,
        default=RecurrenceFrequency.NONE,
    )
    recurrence_end_date = models.DateField(_('Recurrence End Date'), null=True, blank=True)

    # Connections
    tasks = models.ManyToManyField(
        'tasks.Task',
        blank=True,
        related_name='compliance_deadlines',
        verbose_name=_('Connected Tasks'),
    )
    documents = models.ManyToManyField(
        'documents.Document',
        blank=True,
        related_name='compliance_deadlines',
        verbose_name=_('Connected Documents'),
    )

    class Meta:
        verbose_name = _('Compliance Deadline')
        verbose_name_plural = _('Compliance Deadlines')
        ordering = ['due_date_ad', '-priority']

    def __str__(self):
        client_name = f" - {self.client.name}" if self.client else ""
        period_str = f" [{self.period}]" if self.period else ""
        return f"{self.title}{period_str}{client_name} - BS {self.due_date_bs}"

    @property
    def is_overdue(self):
        """Returns True if deadline has passed and is not filed/completed/cancelled."""
        if self.status in [self.Status.COMPLETED, self.Status.FILED, self.Status.CANCELLED]:
            return False
        return self.due_date_ad < timezone.localdate()

    @property
    def days_remaining(self):
        """Returns days remaining until due date."""
        return (self.due_date_ad - timezone.localdate()).days

    @property
    def workflow_stage_index(self):
        """
        Calculates workflow stage progression index (1 to 6):
        1: Deadline (UPCOMING)
        2: Preparation (IN_PROGRESS, WAITING_FOR_CLIENT)
        3: Documents (has attached documents)
        4: Review (READY_FOR_REVIEW)
        5: Filing (FILED)
        6: Completed (COMPLETED)
        """
        if self.status == self.Status.COMPLETED:
            return 6
        if self.status == self.Status.FILED:
            return 5
        if self.status == self.Status.READY_FOR_REVIEW:
            return 4
        if self.documents.exists() or self.status in [self.Status.IN_PROGRESS, self.Status.WAITING_FOR_CLIENT]:
            return 3 if self.documents.exists() else 2
        return 1

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValidationError({'client': _('Client must belong to the same firm as the compliance deadline.')})
        if self.compliance_type_id and self.firm_id and self.compliance_type.firm_id != self.firm_id:
            raise ValidationError({'compliance_type': _('Compliance type must belong to the same firm.')})
        if self.assigned_to and not self.assigned_to.firm_memberships.filter(firm_id=self.firm_id, is_active=True).exists():
            raise ValidationError({'assigned_to': _('Assigned staff must be an active member of the firm.')})
        if self.reviewer and not self.reviewer.firm_memberships.filter(firm_id=self.firm_id, is_active=True).exists():
            raise ValidationError({'reviewer': _('Reviewer must be an active member of the firm.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this compliance deadline.'))
        if self.compliance_type_id and self.firm_id and self.compliance_type.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a compliance type from another firm.'))
        super().save(*args, **kwargs)


class ComplianceActivity(FirmAwareModel):
    """
    Immutable audit history of compliance workflow steps and status changes.
    """
    deadline = models.ForeignKey(
        ComplianceDeadline,
        on_delete=models.CASCADE,
        related_name='activities',
    )
    action = models.CharField(max_length=50)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    description = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='compliance_actions',
    )

    class Meta:
        verbose_name = _('Compliance Activity')
        verbose_name_plural = _('Compliance Activities')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.deadline.title} - {self.action} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
