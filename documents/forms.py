from django import forms
from django.utils.translation import gettext_lazy as _
from clients.models import Client
from documents.models import Document, DocumentRequest
from documents.validators import validate_document_file

FISCAL_YEAR_CHOICES = [
    ('2082/83', 'FY 2082/83'),
    ('2081/82', 'FY 2081/82 (Current)'),
    ('2080/81', 'FY 2080/81'),
    ('2079/80', 'FY 2079/80'),
    ('2078/79', 'FY 2078/79'),
    ('2077/78', 'FY 2077/78'),
]


class DocumentUploadForm(forms.ModelForm):
    """
    Firm-scoped document upload form for Chartered Accountancy practices.
    """
    class Meta:
        model = Document
        fields = ['title', 'client', 'category', 'fiscal_year', 'expiry_date', 'description', 'file']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. FY 2080/81 Signed Audit Report & Financials',
                'required': 'required',
            }),
            'category': forms.Select(attrs={'class': 'cf-select'}),
            'fiscal_year': forms.Select(choices=FISCAL_YEAR_CHOICES, attrs={'class': 'cf-select'}),
            'expiry_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
                'placeholder': 'YYYY-MM-DD',
            }),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
                'placeholder': 'Optional internal notes, IRD voucher numbers, or audit scope references...',
            }),
            'file': forms.FileInput(attrs={'class': 'cf-input', 'required': 'required'}),
        }

    def __init__(self, *args, firm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.firm = firm
        if firm:
            self.fields['client'].queryset = Client.objects.filter(firm=firm, is_active=True).order_by('name')
        else:
            self.fields['client'].queryset = Client.objects.none()
        self.fields['client'].widget.attrs.update({'class': 'cf-select', 'required': 'required'})

    def clean_file(self):
        file = self.cleaned_data.get('file')
        return validate_document_file(file)

    def clean_client(self):
        client = self.cleaned_data.get('client')
        if self.firm and client and client.firm_id != self.firm.id:
            raise forms.ValidationError(_("Selected client does not belong to the active practice."))
        return client


class DocumentEditForm(forms.ModelForm):
    """
    Form to edit metadata and rename an existing document.
    """
    class Meta:
        model = Document
        fields = ['title', 'category', 'fiscal_year', 'status', 'expiry_date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'required': 'required',
            }),
            'category': forms.Select(attrs={'class': 'cf-select'}),
            'fiscal_year': forms.Select(choices=FISCAL_YEAR_CHOICES, attrs={'class': 'cf-select'}),
            'status': forms.Select(attrs={'class': 'cf-select'}),
            'expiry_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
            }),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
            }),
        }


class DocumentRequestForm(forms.ModelForm):
    """
    Staff form to send document submission requests to clients.
    """
    class Meta:
        model = DocumentRequest
        fields = ['client', 'requested_documents', 'due_date', 'notes']
        widgets = {
            'requested_documents': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Bank Statements (Ashoj 2081), Trial Balance, VAT Purchase Book',
                'required': 'required',
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
                'required': 'required',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 3,
                'placeholder': 'Instructions for the client regarding formats, signatures, or supporting ledgers...',
            }),
        }

    def __init__(self, *args, firm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.firm = firm
        if firm:
            self.fields['client'].queryset = Client.objects.filter(firm=firm, is_active=True).order_by('name')
        else:
            self.fields['client'].queryset = Client.objects.none()
        self.fields['client'].widget.attrs.update({'class': 'cf-select', 'required': 'required'})

    def clean_client(self):
        client = self.cleaned_data.get('client')
        if self.firm and client and client.firm_id != self.firm.id:
            raise forms.ValidationError(_("Selected client does not belong to the active practice."))
        return client


class DocumentRequestStatusForm(forms.ModelForm):
    """
    Staff form to update the status of a document request.
    """
    class Meta:
        model = DocumentRequest
        fields = ['status', 'due_date', 'notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'cf-select'}),
            'due_date': forms.DateInput(attrs={'class': 'cf-input', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'cf-input', 'rows': 2}),
        }


class ClientPortalFulfillRequestForm(forms.Form):
    """
    Client portal submission form to upload a file satisfying a pending document request.
    """
    file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'cf-input', 'required': 'required'}),
        label=_('Select Document File'),
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'cf-input',
            'rows': 2,
            'placeholder': 'Optional remarks or explanatory notes for your accountant...',
        }),
        required=False,
        label=_('Client Notes / Remarks'),
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        return validate_document_file(file)
