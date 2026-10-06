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

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'client': _('Client must belong to the same firm as the conversation.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this conversation.'))
        super().save(*args, **kwargs)


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
