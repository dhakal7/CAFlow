from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class Client(FirmAwareModel):
    """
    Client Entity representing business entities, NGOs, or individuals served by the CA Firm.
    """
    class ClientType(models.TextChoices):
        PVT_LTD = 'PVT_LTD', _('Private Limited Company')
        PUB_LTD = 'PUB_LTD', _('Public Limited Company')
        PROPRIETORSHIP = 'PROPRIETORSHIP', _('Proprietorship Business')
        PARTNERSHIP = 'PARTNERSHIP', _('Partnership Firm')
        NGO_INGO = 'NGO_INGO', _('NGO / INGO / Non-Profit')
        INDIVIDUAL = 'INDIVIDUAL', _('Individual Taxpayer')

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active Client')
        ONBOARDING = 'ONBOARDING', _('Onboarding')
        SUSPENDED = 'SUSPENDED', _('Suspended / Under Review')
        ARCHIVED = 'ARCHIVED', _('Archived / Inactive')

    name = models.CharField(_('Client Name / Trade Name'), max_length=255)
    pan_number = models.CharField(
        _('IRD PAN Number'),
        max_length=15,
        blank=True,
        db_index=True,
        help_text=_('9-Digit Inland Revenue Department PAN Number'),
    )
    registration_number = models.CharField(
        _('Company Registrar (OCR) Reg No'),
        max_length=50,
        blank=True,
    )
    client_type = models.CharField(
        _('Client Category'),
        max_length=30,
        choices=ClientType.choices,
        default=ClientType.PVT_LTD,
    )
    contact_person = models.CharField(_('Contact Person / Director'), max_length=200, blank=True)
    email = models.EmailField(_('Primary Email'), blank=True)
    phone = models.CharField(_('Official Phone / Mobile'), max_length=30, blank=True)
    address = models.CharField(_('Registered Address'), max_length=255, blank=True)
    city = models.CharField(_('City / District'), max_length=100, default='Kathmandu')
    status = models.CharField(
        _('Client Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    assigned_manager = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_clients',
        verbose_name=_('Engagement Lead / Manager'),
    )

    class Meta:
        verbose_name = _('Client')
        verbose_name_plural = _('Clients')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (PAN: {self.pan_number or 'N/A'})"
