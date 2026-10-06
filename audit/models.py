from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    """
    Immutable activity and audit trail for client confidentiality,
    practice security, and ICAN review readiness.
    """
    class ActionType(models.TextChoices):
        LOGIN = 'LOGIN', _('User Sign In')
        LOGOUT = 'LOGOUT', _('User Sign Out')
        REGISTER = 'REGISTER', _('Firm Registration')
        INVITE_SENT = 'INVITE_SENT', _('Team Invitation Sent')
        INVITE_ACCEPTED = 'INVITE_ACCEPTED', _('Team Invitation Accepted')
        INVITE_REVOKED = 'INVITE_REVOKED', _('Team Invitation Revoked')
        ROLE_CHANGE = 'ROLE_CHANGE', _('Member Role Changed')
        MEMBER_DEACTIVATED = 'MEMBER_DEACTIVATED', _('Member Deactivated')
        MEMBER_ACTIVATED = 'MEMBER_ACTIVATED', _('Member Activated')
        PROFILE_UPDATE = 'PROFILE_UPDATE', _('Profile Updated')
        FIRM_UPDATE = 'FIRM_UPDATE', _('Firm Settings Updated')
        EMAIL_VERIFIED = 'EMAIL_VERIFIED', _('Email Verified')
        PASSWORD_RESET_REQ = 'PASSWORD_RESET_REQ', _('Password Reset Requested')
        PASSWORD_RESET = 'PASSWORD_RESET', _('Password Reset Completed')
        PASSWORD_CHANGE = 'PASSWORD_CHANGE', _('Password Changed')
        CREATE = 'CREATE', _('Created Record')
        UPDATE = 'UPDATE', _('Updated Record')
        DELETE = 'DELETE', _('Deleted Record')
        VIEW = 'VIEW', _('Viewed Confidential Data')
        EXPORT = 'EXPORT', _('Exported Data')

    firm = models.ForeignKey(
        'firms.Firm',
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions',
    )
    action = models.CharField(_('Action'), max_length=30, choices=ActionType.choices, db_index=True)
    object_type = models.CharField(_('Object Type'), max_length=50, blank=True)
    object_id = models.CharField(_('Object ID'), max_length=100, blank=True)
    description = models.TextField(_('Action Description'))
    ip_address = models.GenericIPAddressField(_('Client IP Address'), null=True, blank=True)
    user_agent = models.CharField(_('Browser / Device Info'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('Audit Log Entry')
        verbose_name_plural = _('Audit Log Entries')
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.action}] {self.description[:40]} by {self.user} at {self.created_at}"
