import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier for auth."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email).lower()
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user model for CAFlow.
    Email is the primary login identifier; usernames are not used.
    """
    username = None  # Completely disable username in favor of email
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    phone = models.CharField(_('Phone Number'), max_length=30, blank=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    # Email verification & security
    is_email_verified = models.BooleanField(_('Email Verified'), default=False)
    email_verification_token = models.CharField(_('Verification Token'), max_length=100, blank=True, default='')

    # Nepal CA Professional Accreditation
    ican_membership_no = models.CharField(
        _('ICAN Membership / Reg No'),
        max_length=50,
        blank=True,
        help_text=_('Institute of Chartered Accountants of Nepal Membership or Registration Number.'),
    )

    # Legacy/compatibility field (multi-tenant relationships are primary through FirmMembership)
    firm = models.ForeignKey(
        'firms.Firm',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legacy_users',
        help_text=_('Cached or legacy default firm.'),
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['first_name', 'last_name', 'email']

    def __str__(self):
        return self.get_display_name()

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.email.split('@')[0].replace('.', ' ').title()

    @property
    def avatar(self):
        """Backwards compatibility alias for profile_photo."""
        return self.profile_photo

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    def get_display_name(self):
        return self.full_name

    def get_role_display(self):
        """Returns the display role for the user in their active firm."""
        membership = getattr(self, '_active_membership', None)
        if membership:
            return membership.get_role_display()
        active_m = self.firm_memberships.filter(status='ACTIVE').first()
        if active_m:
            return active_m.get_role_display()
        if self.is_superuser:
            return 'Platform Superuser'
        return 'Team Member'

    @property
    def is_client_user(self):
        """Checks if user represents an external client rather than internal firm staff."""
        membership = getattr(self, '_active_membership', None)
        if membership:
            return membership.role == 'CLIENT'
        return self.firm_memberships.filter(role='CLIENT').exists()
