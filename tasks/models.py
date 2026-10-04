from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class Task(FirmAwareModel):
    """
    Engagement & Workflow Task tracking for audits, tax filings, and reviews.
    """
    class Status(models.TextChoices):
        TODO = 'TODO', _('To Do')
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        UNDER_REVIEW = 'UNDER_REVIEW', _('Partner / Manager Review')
        COMPLETED = 'COMPLETED', _('Completed')
        BLOCKED = 'BLOCKED', _('Waiting on Client / Blocked')

    class Priority(models.TextChoices):
        LOW = 'LOW', _('Low')
        MEDIUM = 'MEDIUM', _('Medium')
        HIGH = 'HIGH', _('High')
        URGENT = 'URGENT', _('Urgent')

    title = models.CharField(_('Task Title'), max_length=255)
    description = models.TextField(_('Detailed Instructions / Notes'), blank=True)
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='tasks',
        null=True,
        blank=True,
        verbose_name=_('Client Entity'),
    )
    assigned_to = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
        verbose_name=_('Assigned Auditor / Trainee'),
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
        db_index=True,
    )
    priority = models.CharField(
        _('Priority'),
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    due_date = models.DateField(_('Due Date'), null=True, blank=True)
    completed_at = models.DateTimeField(_('Completed Timestamp'), null=True, blank=True)

    class Meta:
        verbose_name = _('Task')
        verbose_name_plural = _('Tasks')
        ordering = ['due_date', '-priority']

    def __str__(self):
        return self.title
