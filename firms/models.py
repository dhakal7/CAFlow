from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel


class Firm(TimeStampedModel):
    """
    Represents a Chartered Accountancy Firm operating on CAFlow (Multi-tenant partition).
    """
    class FirmType(models.TextChoices):
        PROPRIETORSHIP = 'PROPRIETORSHIP', _('Sole Proprietorship Practice')
        PARTNERSHIP = 'PARTNERSHIP', _('Partnership Firm (CA/FCA)')
        LLP = 'LLP', _('Limited Liability Partnership')

    class SubscriptionTier(models.TextChoices):
        SOLO = 'SOLO', _('Solo Practitioner')
        GROWTH = 'GROWTH', _('Growth Firm')
        ENTERPRISE = 'ENTERPRISE', _('Enterprise / Multi-Branch')

    class SubscriptionStatus(models.TextChoices):
        TRIAL = 'TRIAL', _('Free Trial (14 Days)')
        ACTIVE = 'ACTIVE', _('Active Subscription')
        PAST_DUE = 'PAST_DUE', _('Payment Past Due')
        CANCELLED = 'CANCELLED', _('Cancelled')

    name = models.CharField(_('Firm Name'), max_length=255)
    slug = models.SlugField(_('Workspace URL Slug'), max_length=255, unique=True)
    firm_type = models.CharField(
        _('Legal Entity Type'),
        max_length=30,
        choices=FirmType.choices,
        default=FirmType.PARTNERSHIP,
    )
    ican_firm_reg_no = models.CharField(
        _('ICAN Firm Registration No.'),
        max_length=60,
        blank=True,
        help_text=_('Registration number issued by Institute of Chartered Accountants of Nepal'),
    )
    pan_number = models.CharField(
        _('Firm PAN Number'),
        max_length=15,
        blank=True,
        help_text=_('9-digit Inland Revenue Department (IRD) PAN'),
    )
    email = models.EmailField(_('Official Contact Email'), blank=True)
    phone = models.CharField(_('Contact Phone / Mobile'), max_length=30, blank=True)
    address = models.CharField(_('Office Address'), max_length=255, blank=True)
    city = models.CharField(_('City / Municipality'), max_length=100, default='Kathmandu')
    country = models.CharField(_('Country'), max_length=100, default='Nepal')

    current_fiscal_year = models.CharField(
        _('Active Fiscal Year'),
        max_length=20,
        default='2081/82',
        help_text=_('Bikram Sambat Fiscal Year (e.g. 2081/82)'),
    )
    logo = models.ImageField(upload_to='firm_logos/', blank=True, null=True)

    subscription_tier = models.CharField(
        _('Plan Tier'),
        max_length=20,
        choices=SubscriptionTier.choices,
        default=SubscriptionTier.GROWTH,
    )
    subscription_status = models.CharField(
        _('Subscription Status'),
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
    )
    max_staff_seats = models.PositiveIntegerField(_('Staff Seat Allocation'), default=15)

    class Meta:
        verbose_name = _('CA Firm')
        verbose_name_plural = _('CA Firms')
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Firm.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class FirmMember(TimeStampedModel):
    """
    Association between a User and a Firm with explicit firm-level roles.
    """
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='firm_memberships')
    is_primary_contact = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Firm Member')
        verbose_name_plural = _('Firm Members')
        unique_together = ('firm', 'user')

    def __str__(self):
        return f"{self.user} @ {self.firm}"
