from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    """
    Immutable activity and audit trail for client confidentiality and ICAN review readiness.
    """
    class ActionType(models.TextChoices):
        CREATE = 'CREATE', _('Created Record')
        UPDATE = 'UPDATE', _('Updated Record')
        DELETE = 'DELETE', _('Deleted Record')
        VIEW = 'VIEW', _('Viewed Confidential Data')
        EXPORT = 'EXPORT', _('Exported Report / Data')
        LOGIN = 'LOGIN', _('User Authentication')
        LOGOUT = 'LOGOUT', _('User Sign Out')

    firm = models.ForeignKey(
        'firms.Firm',
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions',
    )
    action = models.CharField(_('Action'), max_length=20, choices=ActionType.choices)
    module = models.CharField(_('Module / Context'), max_length=50)
    description = models.TextField(_('Action Description'))
    ip_address = models.GenericIPAddressField(_('Client IP Address'), null=True, blank=True)
    user_agent = models.CharField(_('Browser / Device Info'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('Audit Log Entry')
        verbose_name_plural = _('Audit Log Entries')
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.action}] {self.module} by {self.user} at {self.created_at}"
