import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    ``created_at`` and ``updated_at`` fields along with an ``is_active`` flag.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    is_active = models.BooleanField(_('Is Active'), default=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class FirmAwareQuerySet(models.QuerySet):
    """QuerySet providing automatic tenant scoping helpers."""
    def for_firm(self, firm):
        if not firm:
            return self.none()
        return self.filter(firm=firm)


class FirmAwareManager(models.Manager.from_queryset(FirmAwareQuerySet)):
    """Manager ensuring strict tenant isolation query operations."""
    def for_firm(self, firm):
        return self.get_queryset().for_firm(firm)


class FirmAwareModel(TimeStampedModel):
    """
    Abstract multi-tenant base model for CAFlow.
    Ensures every tenant record is strictly associated with a firm.
    All cross-tenant access must be prevented.
    """
    firm = models.ForeignKey(
        'firms.Firm',
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
        verbose_name=_('Chartered Accountancy Firm'),
        db_index=True,
    )

    objects = FirmAwareManager()

    class Meta:
        abstract = True
