import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel, TimeStampedModel


class WorkflowTemplate(FirmAwareModel):
    """
    Reusable workflow checklists for statutory, tax, and audit procedures in Nepal CA practice.
    e.g. Monthly VAT Workflow, Quarterly TDS Review, Annual Statutory Audit.
    """
    title = models.CharField(_('Template Title'), max_length=255)
    description = models.TextField(_('Template Description'), blank=True)
    service = models.CharField(_('Practice Service'), max_length=100, blank=True)
    default_priority = models.CharField(
        _('Default Priority'),
        max_length=20,
        default='MEDIUM',
    )
    estimated_days = models.PositiveIntegerField(_('Estimated Duration (Days)'), default=7)
    is_system = models.BooleanField(_('System Template'), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_workflow_templates',
    )

    class Meta:
        verbose_name = _('Workflow Template')
        verbose_name_plural = _('Workflow Templates')
        ordering = ['title']

    def __str__(self):
        return self.title


class WorkflowTemplateItem(models.Model):
    """
    Individual checklist steps contained in a reusable workflow template.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name='items',
    )
    title = models.CharField(_('Checklist Item Title'), max_length=255)
    order = models.PositiveIntegerField(_('Order Index'), default=0)

    class Meta:
        verbose_name = _('Workflow Template Item')
        verbose_name_plural = _('Workflow Template Items')
        ordering = ['order', 'title']

    def __str__(self):
        return f"{self.order}. {self.title}"


class Task(FirmAwareModel):
    """
    Engagement & Workflow Task tracking for audits, tax filings, and reviews.
    """
    class Status(models.TextChoices):
        TODO = 'TODO', _('To Do')
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        BLOCKED = 'BLOCKED', _('Waiting')
        UNDER_REVIEW = 'UNDER_REVIEW', _('Review')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')

    # Aliases for board columns and clean code
    PENDING = Status.TODO
    REVIEW = Status.UNDER_REVIEW
    WAITING = Status.BLOCKED

    class Priority(models.TextChoices):
        LOW = 'LOW', _('Low')
        MEDIUM = 'MEDIUM', _('Medium')
        HIGH = 'HIGH', _('High')
        URGENT = 'URGENT', _('Urgent')

    class RecurrenceInterval(models.TextChoices):
        NONE = 'NONE', _('None (One-time)')
        DAILY = 'DAILY', _('Daily')
        WEEKLY = 'WEEKLY', _('Weekly')
        MONTHLY = 'MONTHLY', _('Monthly')
        QUARTERLY = 'QUARTERLY', _('Quarterly')
        YEARLY = 'YEARLY', _('Yearly')
        CUSTOM = 'CUSTOM', _('Custom')

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
    service = models.CharField(
        _('Subscribed Service'),
        max_length=100,
        blank=True,
        help_text=_('Associated CA service, e.g. Tax Compliance & VAT Filing'),
    )
    category = models.CharField(_('Category'), max_length=100, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
        verbose_name=_('Assigned Auditor / Staff'),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tasks',
        verbose_name=_('Created By'),
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
        db_index=True,
    )
    start_date = models.DateField(_('Start Date'), null=True, blank=True)
    due_date = models.DateField(_('Due Date'), null=True, blank=True, db_index=True)
    estimated_hours = models.DecimalField(
        _('Estimated Time (Hours)'),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(_('Completed Timestamp'), null=True, blank=True)

    # Recurrence configuration
    is_recurring = models.BooleanField(_('Is Recurring'), default=False)
    recurrence_interval = models.CharField(
        _('Recurrence Interval'),
        max_length=20,
        choices=RecurrenceInterval.choices,
        default=RecurrenceInterval.NONE,
        blank=True,
    )
    recurrence_end_date = models.DateField(_('Recurrence End Date'), null=True, blank=True)
    custom_recurrence_days = models.PositiveIntegerField(
        _('Custom Recurrence Interval (Days)'),
        null=True,
        blank=True,
    )

    # Workflow template origin
    template_applied = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='spawned_tasks',
    )

    class Meta:
        verbose_name = _('Task')
        verbose_name_plural = _('Tasks')
        ordering = ['due_date', '-priority']

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'client': _('Client must belong to the same firm as the task.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this task.'))
        super().save(*args, **kwargs)

    @property
    def checklist_stats(self):
        """Returns completed count, total count, and completion percentage."""
        items = list(self.checklist_items.all())
        total = len(items)
        if total == 0:
            return {'completed': 0, 'total': 0, 'percent': 0, 'has_items': False}
        completed = sum(1 for item in items if item.is_completed)
        percent = int(round((completed / total) * 100))
        return {
            'completed': completed,
            'total': total,
            'percent': percent,
            'has_items': True,
        }

    @property
    def progress_percent(self):
        """Calculates progress percent from checklist items or completion status."""
        stats = self.checklist_stats
        if stats['has_items']:
            return stats['percent']
        if self.status == self.Status.COMPLETED:
            return 100
        elif self.status == self.Status.UNDER_REVIEW:
            return 75
        elif self.status == self.Status.IN_PROGRESS:
            return 40
        return 0

    @property
    def is_overdue(self):
        """Returns True if task is past due date and not completed."""
        if self.status == self.Status.COMPLETED or not self.due_date:
            return False
        return self.due_date < timezone.localdate()

    @property
    def days_remaining(self):
        """Returns integer days remaining until due date, or None."""
        if not self.due_date:
            return None
        delta = (self.due_date - timezone.localdate()).days
        return delta

    @property
    def status_badge_class(self):
        """Consistent status badge class conforming to CAFlow design system."""
        badges = {
            self.Status.TODO: 'cf-badge-muted',
            self.Status.IN_PROGRESS: 'cf-badge-warning',
            self.Status.BLOCKED: 'cf-badge-secondary',
            self.Status.UNDER_REVIEW: 'cf-badge-primary',
            self.Status.COMPLETED: 'cf-badge-success',
            self.Status.CANCELLED: 'cf-badge-danger',
        }
        return badges.get(self.status, 'cf-badge-secondary')

    @property
    def priority_badge_class(self):
        """Consistent priority badge class conforming to CAFlow design system."""
        badges = {
            self.Priority.LOW: 'cf-badge-muted',
            self.Priority.MEDIUM: 'cf-badge-secondary',
            self.Priority.HIGH: 'cf-badge-warning',
            self.Priority.URGENT: 'cf-badge-danger',
        }
        return badges.get(self.priority, 'cf-badge-secondary')


class TaskChecklistItem(FirmAwareModel):
    """
    Subtask checklist item within a task.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='checklist_items',
    )
    title = models.CharField(_('Checklist Item Title'), max_length=255)
    is_completed = models.BooleanField(_('Completed'), default=False)
    completed_at = models.DateTimeField(_('Completed Timestamp'), null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_checklist_items',
    )
    order = models.PositiveIntegerField(_('Order Index'), default=0)

    class Meta:
        verbose_name = _('Task Checklist Item')
        verbose_name_plural = _('Task Checklist Items')
        ordering = ['order', 'created_at']

    def __str__(self):
        status = "[x]" if self.is_completed else "[ ]"
        return f"{status} {self.title}"


class TaskComment(FirmAwareModel):
    """
    Internal practice comments and notes on a task.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_comments',
    )
    content = models.TextField(_('Comment Content'))

    class Meta:
        verbose_name = _('Task Comment')
        verbose_name_plural = _('Task Comments')
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.user} on {self.task.title}"


class TaskAttachment(FirmAwareModel):
    """
    Files, working papers, vouchers or documents attached to a task.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(upload_to='tasks/attachments/%Y/%m/')
    filename = models.CharField(_('Original Filename'), max_length=255)
    file_size_bytes = models.PositiveBigIntegerField(_('File Size in Bytes'), default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_task_attachments',
    )

    class Meta:
        verbose_name = _('Task Attachment')
        verbose_name_plural = _('Task Attachments')
        ordering = ['-created_at']

    def __str__(self):
        return self.filename

    @property
    def formatted_size(self):
        """Format bytes into readable KB/MB."""
        size = self.file_size_bytes
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{round(size / 1024, 1)} KB"
        else:
            return f"{round(size / (1024 * 1024), 1)} MB"


class TaskActivity(FirmAwareModel):
    """
    Audit and activity log entries specific to a task.
    """
    class ActionType(models.TextChoices):
        CREATED = 'CREATED', _('Created Task')
        STATUS_CHANGED = 'STATUS_CHANGED', _('Status Changed')
        ASSIGNED = 'ASSIGNED', _('Assigned Staff')
        COMPLETED = 'COMPLETED', _('Completed Task')
        REOPENED = 'REOPENED', _('Reopened Task')
        CHECKLIST_ADDED = 'CHECKLIST_ADDED', _('Added Checklist Item')
        CHECKLIST_TOGGLED = 'CHECKLIST_TOGGLED', _('Checklist Item Toggled')
        CHECKLIST_DELETED = 'CHECKLIST_DELETED', _('Deleted Checklist Item')
        ATTACHMENT_ADDED = 'ATTACHMENT_ADDED', _('Attached Document')
        COMMENT_ADDED = 'COMMENT_ADDED', _('Added Comment')
        UPDATED = 'UPDATED', _('Updated Task Details')
        DELETED = 'DELETED', _('Deleted Task')

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='activities',
    )
    action_type = models.CharField(
        _('Action Type'),
        max_length=40,
        choices=ActionType.choices,
        default=ActionType.UPDATED,
        db_index=True,
    )
    description = models.CharField(_('Description'), max_length=255)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_activities',
    )

    class Meta:
        verbose_name = _('Task Activity')
        verbose_name_plural = _('Task Activities')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action_type}: {self.description}"
