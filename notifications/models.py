from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import TimeStampedModel


class Notification(TimeStampedModel):
    """
    In-app alert for assignments, impending IRD deadlines, approvals, or messages.
    """
    class NotificationType(models.TextChoices):
        TASK = 'TASK', _('Task Assigned / Updated')
        COMPLIANCE = 'COMPLIANCE', _('Compliance Filing Due')
        DOCUMENT = 'DOCUMENT', _('Document Uploaded / Requested')
        BILLING = 'BILLING', _('Invoice / Payment')
        SYSTEM = 'SYSTEM', _('System Alert')

    recipient = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    firm = models.ForeignKey(
        'firms.Firm',
        on_delete=models.CASCADE,
        related_name='firm_notifications',
        null=True,
        blank=True,
    )
    title = models.CharField(_('Notification Title'), max_length=255)
    message = models.TextField(_('Message Body'))
    action_url = models.CharField(_('Action Target URL'), max_length=255, blank=True)
    notification_type = models.CharField(
        _('Type'),
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
    )
    is_read = models.BooleanField(_('Is Read'), default=False)
    read_at = models.DateTimeField(_('Read Timestamp'), null=True, blank=True)

    class Meta:
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient} - {self.title}"
