from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier for auth."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
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
    Supports practice partners, managers, trainees, and client users.
    """
    class Role(models.TextChoices):
        MANAGING_PARTNER = 'MANAGING_PARTNER', _('Managing Partner / FCA')
        PARTNER = 'PARTNER', _('Partner / FCA / ACA')
        AUDIT_MANAGER = 'AUDIT_MANAGER', _('Audit & Tax Manager')
        SENIOR_AUDITOR = 'SENIOR_AUDITOR', _('Senior Audit Associate')
        ARTICLE_TRAINEE = 'ARTICLE_TRAINEE', _('Article Trainee (ICAN)')
        CLIENT_ADMIN = 'CLIENT_ADMIN', _('Client Representative')
        CLIENT_STAFF = 'CLIENT_STAFF', _('Client Accounting Staff')

    username = models.CharField(_('username'), max_length=150, blank=True, null=True)
    email = models.EmailField(_('email address'), unique=True)
    full_name = models.CharField(_('Full Name'), max_length=255, blank=True)
    phone = models.CharField(_('Mobile / Phone Number'), max_length=20, blank=True)
    role = models.CharField(
        _('Firm Role'),
        max_length=30,
        choices=Role.choices,
        default=Role.SENIOR_AUDITOR,
    )
    firm = models.ForeignKey(
        'firms.Firm',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members',
        help_text=_('Primary Chartered Accountancy firm this user belongs to.'),
    )
    is_firm_owner = models.BooleanField(
        _('Firm Owner / Licensee'),
        default=False,
        help_text=_('Whether this user holds primary subscription authority for the firm.'),
    )
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    ican_membership_no = models.CharField(
        _('ICAN Membership / Reg No'),
        max_length=50,
        blank=True,
        help_text=_('Institute of Chartered Accountants of Nepal Membership or Registration Number.'),
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['full_name', 'email']

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        return self.full_name or self.email.split('@')[0].replace('.', ' ').title()

    @property
    def role_badge_class(self):
        badges = {
            self.Role.MANAGING_PARTNER: 'badge-primary',
            self.Role.PARTNER: 'badge-primary',
            self.Role.AUDIT_MANAGER: 'badge-warning',
            self.Role.SENIOR_AUDITOR: 'badge-secondary',
            self.Role.ARTICLE_TRAINEE: 'badge-muted',
            self.Role.CLIENT_ADMIN: 'badge-success',
            self.Role.CLIENT_STAFF: 'badge-muted',
        }
        return badges.get(self.role, 'badge-secondary')
