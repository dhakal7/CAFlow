from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class Invoice(FirmAwareModel):
    """
    Practice Billing and Professional Fee Invoices with Nepal 13% VAT and TDS support.
    """
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        ISSUED = 'ISSUED', _('Issued to Client')
        PARTIAL = 'PARTIAL', _('Partially Settled')
        PAID = 'PAID', _('Paid in Full')
        CANCELLED = 'CANCELLED', _('Cancelled / Void')

    invoice_number = models.CharField(_('Invoice Serial #'), max_length=50)
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='invoices',
        verbose_name=_('Client Entity'),
    )
    subtotal_npr = models.DecimalField(_('Fee Subtotal (NPR)'), max_digits=12, decimal_places=2, default=Decimal('0.00'))
    vat_percent = models.DecimalField(_('VAT %'), max_digits=5, decimal_places=2, default=Decimal('13.00'))
    vat_amount_npr = models.DecimalField(_('VAT Amount (NPR)'), max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount_npr = models.DecimalField(_('Total Payable (NPR)'), max_digits=12, decimal_places=2, default=Decimal('0.00'))
    paid_amount_npr = models.DecimalField(_('Amount Received (NPR)'), max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(
        _('Payment Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    issue_date = models.DateField(_('Date of Issue'))
    due_date = models.DateField(_('Payment Due Date'))

    class Meta:
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-issue_date']

    def __str__(self):
        return f"INV-{self.invoice_number} ({self.client.name})"

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'client': _('Client must belong to the same firm as the invoice.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this invoice.'))
        super().save(*args, **kwargs)
