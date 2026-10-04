from django.db import models
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
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
    )
    file_size_bytes = models.PositiveBigIntegerField(_('File Size in Bytes'), default=0)

    class Meta:
        verbose_name = _('Document')
        verbose_name_plural = _('Documents')
        ordering = ['-created_at']

    def __str__(self):
        return self.title
