import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel


class FirmRole(models.TextChoices):
    """
    Standardized roles across CAFlow practice management.
    """
    OWNER = 'OWNER', _('Firm Owner')
    ADMIN = 'ADMIN', _('Practice Administrator')
    CA = 'CA', _('Chartered Accountant (CA/FCA)')
    SENIOR = 'SENIOR', _('Senior Associate')
    ACCOUNTANT = 'ACCOUNTANT', _('Accountant')
    STAFF = 'STAFF', _('Staff / Trainee')
    CLIENT = 'CLIENT', _('Client Representative')


class MembershipStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    INVITED = 'INVITED', _('Invited')
    SUSPENDED = 'SUSPENDED', _('Suspended')
    INACTIVE = 'INACTIVE', _('Inactive')


class Firm(TimeStampedModel):
    """
    Represents a Chartered Accountancy Firm operating on CAFlow (Multi-tenant partition).
    Every tenant resource belongs to a Firm.
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
    slug = models.SlugField(_('Workspace URL Slug'), max_length=255, unique=True, db_index=True)
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

    # Localization
    timezone = models.CharField(_('Timezone'), max_length=50, default='Asia/Kathmandu')
    currency = models.CharField(_('Currency'), max_length=10, default='NPR')
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
            base_slug = slugify(self.name) or 'firm'
            slug = base_slug
            counter = 1
            while Firm.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def owner(self):
        membership = self.memberships.filter(role=FirmRole.OWNER, status=MembershipStatus.ACTIVE).first()
        return membership.user if membership else None

    @property
    def active_members_count(self):
        return self.memberships.filter(status=MembershipStatus.ACTIVE).count()


class FirmMembership(TimeStampedModel):
    """
    Explicit association between a User and a Firm with strict server-enforced roles.
    A user can belong to multiple firms, with one active firm at a time.
    """
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='firm_memberships')
    role = models.CharField(
        _('Firm Role'),
        max_length=20,
        choices=FirmRole.choices,
        default=FirmRole.STAFF,
    )
    status = models.CharField(
        _('Membership Status'),
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
    )
    joined_at = models.DateTimeField(_('Joined At'), default=timezone.now)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_firm_memberships',
    )
    is_primary_contact = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Firm Membership')
        verbose_name_plural = _('Firm Memberships')
        constraints = [
            models.UniqueConstraint(fields=['firm', 'user'], name='unique_firm_user_membership')
        ]
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()}) @ {self.firm.name}"

    @property
    def role_badge_class(self):
        badges = {
            FirmRole.OWNER: 'cf-badge-primary',
            FirmRole.ADMIN: 'cf-badge-primary',
            FirmRole.CA: 'cf-badge-warning',
            FirmRole.SENIOR: 'cf-badge-secondary',
            FirmRole.ACCOUNTANT: 'cf-badge-secondary',
            FirmRole.STAFF: 'cf-badge-muted',
            FirmRole.CLIENT: 'cf-badge-success',
        }
        return badges.get(self.role, 'cf-badge-secondary')

    @property
    def status_badge_class(self):
        badges = {
            MembershipStatus.ACTIVE: 'cf-badge-success',
            MembershipStatus.INVITED: 'cf-badge-warning',
            MembershipStatus.SUSPENDED: 'cf-badge-danger',
            MembershipStatus.INACTIVE: 'cf-badge-muted',
        }
        return badges.get(self.status, 'cf-badge-secondary')


# Backwards compatibility alias
FirmMember = FirmMembership


class FirmInvitation(TimeStampedModel):
    """
    Invitation token for onboarding new staff or clients into a specific Firm.
    """
    firm = models.ForeignKey(Firm, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField(_('Invited Email'))
    role = models.CharField(
        _('Assigned Role'),
        max_length=20,
        choices=FirmRole.choices,
        default=FirmRole.STAFF,
    )
    token = models.CharField(_('Secure Token'), max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_invitations',
    )
    expires_at = models.DateTimeField(_('Expires At'))
    is_accepted = models.BooleanField(_('Is Accepted'), default=False)
    accepted_at = models.DateTimeField(_('Accepted At'), null=True, blank=True)

    class Meta:
        verbose_name = _('Firm Invitation')
        verbose_name_plural = _('Firm Invitations')
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite for {self.email} ({self.role}) to {self.firm.name}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at
