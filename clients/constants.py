"""
Constants and configuration for CAFlow Client CRM Module.
Tailored for Nepal Chartered Accountancy Practice Standards.
"""

from django.utils.translation import gettext_lazy as _

SERVICE_CHOICES = [
    ('STATUTORY_AUDIT', _('Statutory Audit (NFRS/NAS)')),
    ('TAX_VAT', _('Tax Compliance & VAT Filing')),
    ('BOOKKEEPING', _('Accounting & Bookkeeping')),
    ('OCR_COMPLIANCE', _('Company Registrar (OCR) Annual Filing')),
    ('INTERNAL_AUDIT', _('Internal Audit & Risk Advisory')),
    ('TDS_WITHHOLDING', _('TDS Reconciliation & Withholding Tax')),
    ('ADVISORY', _('Financial Due Diligence & Advisory')),
]

SERVICE_DICT = dict(SERVICE_CHOICES)

BUSINESS_TYPE_CHOICES = [
    ('PVT_LTD', _('Private Limited Company')),
    ('PUB_LTD', _('Public Limited Company')),
    ('PROPRIETORSHIP', _('Proprietorship Business')),
    ('PARTNERSHIP', _('Partnership Firm')),
    ('NGO_INGO', _('NGO / INGO / Non-Profit')),
    ('INDIVIDUAL', _('Individual Taxpayer')),
]

FISCAL_YEAR_CHOICES = [
    ('2081/82', 'FY 2081/82 (Current)'),
    ('2080/81', 'FY 2080/81'),
    ('2079/80', 'FY 2079/80'),
    ('2082/83', 'FY 2082/83 (Upcoming)'),
]
