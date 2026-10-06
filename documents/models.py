import os
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class Document(FirmAwareModel):
    """
    Firm & Client Document Repository (Financial statements, tax filings, bills, vouchers).
    """
    class Category(models.TextChoices):
        TAX_FILING = 'TAX_FILING', _('IRD Tax Filing / Returns')
        AUDIT_WORKING_PAPERS = 'AUDIT_WORKING_PAPERS', _('Audit Working Papers')
        FINANCIAL_STATEMENTS = 'FINANCIAL_STATEMENTS', _('Financial Statements (NFRS/NAS)')
        VAT_SALES_PURCHASE = 'VAT_SALES_PURCHASE', _('VAT Purchase & Sales Books')
        COMPANY_REGISTRAR = 'COMPANY_REGISTRAR', _('Company Registrar (OCR) Docs')
        LEGAL_CONTRACTS = 'LEGAL_CONTRACTS', _('Agreements & Minutes')
        OTHER = 'OTHER', _('General / Miscellaneous')

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        ARCHIVED = 'ARCHIVED', _('Archived')

    title = models.CharField(_('Document Title'), max_length=255)
    category = models.CharField(
        _('Category'),
        max_length=40,
        choices=Category.choices,
        default=Category.AUDIT_WORKING_PAPERS,
    )
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name=_('Client Entity'),
    )
    file = models.FileField(upload_to='firm_documents/%Y/%m/')
    fiscal_year = models.CharField(_('Fiscal Year'), max_length=20, default='2081/82')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
    )
    file_size_bytes = models.PositiveBigIntegerField(_('File Size in Bytes'), default=0)
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    expiry_date = models.DateField(_('Expiry Date'), null=True, blank=True)
    description = models.TextField(_('Description / Notes'), blank=True)
    file_type = models.CharField(_('File Extension'), max_length=50, blank=True)

    class Meta:
        verbose_name = _('Document')
        verbose_name_plural = _('Documents')
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def file_extension(self):
        if self.file_type:
            return self.file_type.lower()
        if self.file and self.file.name:
            ext = os.path.splitext(self.file.name)[1].lstrip('.').lower()
            return ext
        return ''

    @property
    def can_preview(self):
        return self.file_extension in ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'txt', 'csv', 'json', 'log']

    @property
    def preview_type(self):
        ext = self.file_extension
        if ext == 'pdf':
            return 'pdf'
        if ext in ['png', 'jpg', 'jpeg', 'webp', 'gif']:
            return 'image'
        if ext in ['txt', 'csv', 'json', 'log']:
            return 'text'
        return 'none'

    @property
    def is_expired(self):
        if self.expiry_date:
            return self.expiry_date < timezone.localdate()
        return False

    @property
    def is_expiring_soon(self):
        if self.expiry_date and not self.is_expired:
            return (self.expiry_date - timezone.localdate()).days <= 30
        return False

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValidationError({'client': _('Client must belong to the same firm as the document.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this document.'))
        if self.file:
            try:
                if not self.file_size_bytes or self.file_size_bytes == 0:
                    self.file_size_bytes = self.file.size
            except Exception:
                pass
            if not self.file_type and self.file.name:
                self.file_type = os.path.splitext(self.file.name)[1].lstrip('.').lower()
        super().save(*args, **kwargs)


class DocumentRequest(FirmAwareModel):
    """
    Tracks pending and fulfilled document requests sent to clients.
    """
    class Status(models.TextChoices):
        REQUESTED = 'REQUESTED', _('Requested')
        PENDING = 'PENDING', _('Pending')
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', _('Partially Received')
        RECEIVED = 'RECEIVED', _('Received')
        REJECTED = 'REJECTED', _('Rejected')
        OVERDUE = 'OVERDUE', _('Overdue')
        CANCELLED = 'CANCELLED', _('Cancelled')
        REMINDED = 'REMINDED', _('Reminded')

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='document_requests',
        verbose_name=_('Client Entity'),
    )
    requested_documents = models.CharField(
        _('Requested Documents'),
        max_length=255,
        help_text=_('e.g. Bank Statements, Monthly VAT Purchase Ledger'),
    )
    requested_date = models.DateField(_('Requested Date'), default=timezone.localdate)
    due_date = models.DateField(_('Submission Deadline'))
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_documents',
    )
    received_date = models.DateTimeField(_('Received Date'), null=True, blank=True)
    uploaded_document = models.ForeignKey(
        'documents.Document',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fulfilled_requests',
        verbose_name=_('Uploaded Document'),
    )
    notes = models.TextField(_('Instructions for Client'), blank=True)

    class Meta:
        verbose_name = _('Document Request')
        verbose_name_plural = _('Document Requests')
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return f"{self.requested_documents} - {self.client.name}"

    @property
    def is_overdue(self):
        if self.status in [self.Status.RECEIVED, self.Status.CANCELLED]:
            return False
        return self.due_date < timezone.localdate()

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValidationError({'client': _('Client must belong to the same firm as the document request.')})
        if self.uploaded_document:
            if self.uploaded_document.firm_id != self.firm_id:
                raise ValidationError({'uploaded_document': _('Uploaded document must belong to the same firm.')})
            if self.uploaded_document.client_id != self.client_id:
                raise ValidationError({'uploaded_document': _('Uploaded document must belong to the same client.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this document request.'))
        if self.uploaded_document:
            if self.uploaded_document.firm_id != self.firm_id or self.uploaded_document.client_id != self.client_id:
                raise ValueError(_('Uploaded document does not match firm or client.'))
        super().save(*args, **kwargs)
