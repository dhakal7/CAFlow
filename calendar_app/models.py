from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class CalendarEvent(FirmAwareModel):
    """
    Schedules client audits, tax assessment hearings, and team commitments.
    """
    class EventType(models.TextChoices):
        AUDIT_VISIT = 'AUDIT_VISIT', _('Physical / Field Audit Visit')
        CLIENT_MEETING = 'CLIENT_MEETING', _('Client Review Meeting')
        IRD_HEARING = 'IRD_HEARING', _('Tax Office / IRD Hearing')
        DEADLINE = 'DEADLINE', _('Statutory Filing Deadline')
        INTERNAL_REVIEW = 'INTERNAL_REVIEW', _('Internal Peer Review')

    title = models.CharField(_('Event Title'), max_length=255)
    description = models.TextField(_('Details / Agenda'), blank=True)
    event_type = models.CharField(
        _('Event Type'),
        max_length=30,
        choices=EventType.choices,
        default=EventType.CLIENT_MEETING,
    )
    start_time = models.DateTimeField(_('Start Time'))
    end_time = models.DateTimeField(_('End Time'))
    is_all_day = models.BooleanField(_('All-day Event'), default=False)
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events',
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='created_events',
    )

    class Meta:
        verbose_name = _('Calendar Event')
        verbose_name_plural = _('Calendar Events')
        ordering = ['start_time']

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'client': _('Client must belong to the same firm as the calendar event.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this calendar event.'))
        super().save(*args, **kwargs)
