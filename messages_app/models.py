from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class Conversation(FirmAwareModel):
    """
    Message thread between firm staff and/or clients.
    """
    title = models.CharField(_('Subject / Thread Title'), max_length=255)
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversations',
    )
    participants = models.ManyToManyField('accounts.User', related_name='conversations')

    class Meta:
        verbose_name = _('Conversation')
        verbose_name_plural = _('Conversations')
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class ChatMessage(FirmAwareModel):
    """
    Individual message entry in a conversation thread.
    """
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='sent_messages',
    )
    body = models.TextField(_('Message Body'))

    class Meta:
        verbose_name = _('Chat Message')
        verbose_name_plural = _('Chat Messages')
        ordering = ['created_at']

    def __str__(self):
        return f"From {self.sender}: {self.body[:40]}"
