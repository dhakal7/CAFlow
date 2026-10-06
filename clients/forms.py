import re
from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from firms.models import FirmMembership, MembershipStatus
from clients.models import Client
from clients.constants import SERVICE_CHOICES, FISCAL_YEAR_CHOICES
from tasks.models import Task
from documents.models import DocumentRequest
from messages_app.models import Conversation, ChatMessage


class ClientForm(forms.ModelForm):
    """
    Form supporting both Client Creation (multi-step) and Client Editing.
    Scopes team members strictly to the active Firm.
    """
    services = forms.MultipleChoiceField(
        choices=SERVICE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_('Subscribed CA Practice Services'),
    )
    create_onboarding_tasks = forms.BooleanField(
        required=False,
        initial=True,
        label=_('Generate initial KYC, Tax Clearance & OCR onboarding tasks'),
        help_text=_('Automatically creates compliance verification tasks for the assigned lead.'),
    )

    class Meta:
        model = Client
        fields = [
            # Basic Info
            'name',
            'contact_person',
            'email',
            'phone',
            'address',
            'city',
            # Business Info
            'legal_name',
            'business_name',
            'client_type',
            'pan_number',
            'registration_number',
            'registration_date',
            'tax_registration_date',
            'fiscal_year',
            # Practice Info
            'notes',
            # Services
            'services',
            # Team
            'assigned_manager',
            'assigned_staff',
            # Status
            'status',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'e.g. Ramesh Adhikari (Director / Rep)'}),
            'contact_person': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Full name of primary director / signatory'}),
            'email': forms.EmailInput(attrs={'class': 'cf-input', 'placeholder': 'contact@company.com.np'}),
            'phone': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': '+977-98XXXXXXXX / +977-1-4XXXXXX'}),
            'address': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Ward No., Street, e.g. Putalisadak'}),
            'city': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'Kathmandu / Pokhara / Biratnagar'}),
            'legal_name': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'e.g. Himalayan Enterprises Pvt. Ltd.'}),
            'business_name': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'e.g. Himalayan Traders (Trade Name)'}),
            'client_type': forms.Select(attrs={'class': 'cf-select'}),
            'pan_number': forms.TextInput(attrs={'class': 'cf-input mono-font', 'placeholder': '9-Digit IRD PAN', 'maxlength': '15'}),
            'registration_number': forms.TextInput(attrs={'class': 'cf-input', 'placeholder': 'OCR Registration No. (e.g. 18294/074)'}),
            'registration_date': forms.DateInput(attrs={'class': 'cf-input', 'type': 'date'}),
            'tax_registration_date': forms.DateInput(attrs={'class': 'cf-input', 'type': 'date'}),
            'fiscal_year': forms.Select(choices=FISCAL_YEAR_CHOICES, attrs={'class': 'cf-select'}),
            'notes': forms.Textarea(attrs={'class': 'cf-input', 'rows': 3, 'placeholder': 'Confidential background notes, special tax status, internal remarks...'}),
            'assigned_manager': forms.Select(attrs={'class': 'cf-select'}),
            'assigned_staff': forms.SelectMultiple(attrs={'class': 'cf-select', 'size': '4'}),
            'status': forms.Select(attrs={'class': 'cf-select'}),
        }

    def __init__(self, *args, firm=None, **kwargs):
        self.firm = firm
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            if self.instance.services:
                self.fields['services'].initial = self.instance.services

        # Scope staff and managers strictly to the active firm
        if self.firm:
            firm_users = User.objects.filter(
                firm_memberships__firm=self.firm,
                firm_memberships__status=MembershipStatus.ACTIVE,
                is_active=True,
            ).distinct().order_by('first_name', 'last_name')

            self.fields['assigned_manager'].queryset = firm_users
            self.fields['assigned_staff'].queryset = firm_users
        else:
            self.fields['assigned_manager'].queryset = User.objects.none()
            self.fields['assigned_staff'].queryset = User.objects.none()

        self.fields['assigned_manager'].empty_label = _('Select Engagement Lead (CA / Partner)')
        if 'status' in self.fields:
            self.fields['status'].required = False
            self.fields['status'].initial = Client.Status.ACTIVE

    def clean_pan_number(self):
        pan = self.cleaned_data.get('pan_number', '').strip()
        if not pan:
            return pan
        # Clean non-alphanumeric characters if any
        digits_only = re.sub(r'\D', '', pan)
        if digits_only and len(digits_only) != 9:
            raise forms.ValidationError(_('Nepal IRD PAN number must be exactly 9 digits.'))
        return digits_only or pan

    def clean(self):
        cleaned_data = super().clean()
        biz_name = cleaned_data.get('business_name')
        legal_name = cleaned_data.get('legal_name')
        client_name = cleaned_data.get('name')

        if not biz_name and not legal_name and not client_name:
            raise forms.ValidationError(_('Please provide at least a Legal Name, Business Name, or Client Name.'))

        # Default business_name and legal_name
        if not legal_name and biz_name:
            cleaned_data['legal_name'] = biz_name
        if not biz_name and legal_name:
            cleaned_data['business_name'] = legal_name
        if not biz_name and not legal_name:
            cleaned_data['business_name'] = client_name
            cleaned_data['legal_name'] = client_name
        if not client_name:
            cleaned_data['name'] = cleaned_data.get('business_name') or cleaned_data.get('legal_name')

        if not cleaned_data.get('contact_person'):
            cleaned_data['contact_person'] = cleaned_data.get('name', '')

        if not cleaned_data.get('status'):
            cleaned_data['status'] = Client.Status.ACTIVE

        # Cross-firm validation for manager and staff
        if self.firm:
            mgr = cleaned_data.get('assigned_manager')
            if mgr and (not mgr.is_active or not mgr.firm_memberships.filter(firm=self.firm, status=MembershipStatus.ACTIVE).exists()):
                raise forms.ValidationError({'assigned_manager': _('Assigned manager must belong to this firm.')})

            staff_list = cleaned_data.get('assigned_staff')
            if staff_list:
                for staff_user in staff_list:
                    if not staff_user.is_active or not staff_user.firm_memberships.filter(firm=self.firm, status=MembershipStatus.ACTIVE).exists():
                        raise forms.ValidationError({'assigned_staff': _('All assigned staff must belong to this firm.')})

        return cleaned_data


class AssignStaffForm(forms.Form):
    """Assigns manager and staff associates to a client."""
    assigned_manager = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'cf-select'}),
        label=_('Engagement Lead / Manager (CA)'),
        empty_label=_('Unassigned'),
    )
    assigned_staff = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'cf-select', 'size': '4'}),
        label=_('Assigned Audit & Tax Associates'),
    )

    def __init__(self, *args, firm=None, **kwargs):
        self.firm = firm
        super().__init__(*args, **kwargs)
        if firm:
            firm_users = User.objects.filter(
                firm_memberships__firm=firm,
                firm_memberships__status=MembershipStatus.ACTIVE,
                is_active=True,
            ).distinct().order_by('first_name', 'last_name')
            self.fields['assigned_manager'].queryset = firm_users
            self.fields['assigned_staff'].queryset = firm_users

    def clean(self):
        cleaned_data = super().clean()
        if self.firm:
            mgr = cleaned_data.get('assigned_manager')
            if mgr and (not mgr.is_active or not mgr.firm_memberships.filter(firm=self.firm, status=MembershipStatus.ACTIVE).exists()):
                raise forms.ValidationError({'assigned_manager': _('Assigned manager must belong to this firm.')})
            staff = cleaned_data.get('assigned_staff')
            if staff:
                for s in staff:
                    if not s.is_active or not s.firm_memberships.filter(firm=self.firm, status=MembershipStatus.ACTIVE).exists():
                        raise forms.ValidationError({'assigned_staff': _('Assigned staff must belong to this firm.')})
        return cleaned_data


class RequestDocumentForm(forms.ModelForm):
    """Requests working documents or vouchers from a client."""
    class Meta:
        model = DocumentRequest
        fields = ['requested_documents', 'due_date', 'notes']
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


class CreateClientTaskForm(forms.ModelForm):
    """Creates an operational task tied to a specific client."""
    class Meta:
        model = Task
        fields = ['title', 'assigned_to', 'priority', 'due_date', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Finalize NAS 10 Balance Sheet disclosures',
                'required': 'required',
            }),
            'assigned_to': forms.Select(attrs={'class': 'cf-select'}),
            'priority': forms.Select(attrs={'class': 'cf-select'}),
            'due_date': forms.DateInput(attrs={'class': 'cf-input', 'type': 'date'}),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 3,
                'placeholder': 'Audit procedures, checklists, or work notes...',
            }),
        }

    def __init__(self, *args, firm=None, **kwargs):
        self.firm = firm
        super().__init__(*args, **kwargs)
        if firm:
            self.fields['assigned_to'].queryset = User.objects.filter(
                firm_memberships__firm=firm,
                firm_memberships__status=MembershipStatus.ACTIVE,
                is_active=True,
            ).distinct().order_by('first_name', 'last_name')
            self.fields['assigned_to'].empty_label = _('Select Assignee')

    def clean(self):
        cleaned_data = super().clean()
        if self.firm:
            assigned = cleaned_data.get('assigned_to')
            if assigned and not assigned.firm_memberships.filter(firm=self.firm, status=MembershipStatus.ACTIVE, is_active=True).exists():
                raise forms.ValidationError({'assigned_to': _('Assignee must belong to this firm.')})
        return cleaned_data


class SendMessageForm(forms.Form):
    """Sends a message or note related to a client."""
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'cf-input',
            'placeholder': 'e.g. Regarding Tax Return Filing & Query on Annexure 7',
            'required': 'required',
        }),
        label=_('Subject'),
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'cf-input',
            'rows': 4,
            'placeholder': 'Write message content, statutory advice, or reminder note...',
            'required': 'required',
        }),
        label=_('Message Body'),
    )


class UploadDocumentForm(forms.ModelForm):
    """Uploads a client or firm document to the repository."""
    class Meta:
        from documents.models import Document
        model = Document
        fields = ['title', 'category', 'fiscal_year', 'file']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. FY 2080/81 Audited Balance Sheet & P&L',
                'required': 'required',
            }),
            'category': forms.Select(attrs={'class': 'cf-select'}),
            'fiscal_year': forms.Select(choices=FISCAL_YEAR_CHOICES, attrs={'class': 'cf-select'}),
            'file': forms.FileInput(attrs={'class': 'cf-input', 'required': 'required'}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        from documents.validators import validate_document_file
        return validate_document_file(file)


class CreateInvoiceForm(forms.ModelForm):
    """Generates a billing invoice for the client."""
    class Meta:
        from billing.models import Invoice
        model = Invoice
        fields = ['invoice_number', 'subtotal_npr', 'issue_date', 'due_date', 'status']
        widgets = {
            'invoice_number': forms.TextInput(attrs={
                'class': 'cf-input mono-font',
                'placeholder': 'e.g. 2081-015',
                'required': 'required',
            }),
            'subtotal_npr': forms.NumberInput(attrs={
                'class': 'cf-input mono-font',
                'placeholder': '50000.00',
                'step': '0.01',
                'required': 'required',
            }),
            'issue_date': forms.DateInput(attrs={'class': 'cf-input', 'type': 'date', 'required': 'required'}),
            'due_date': forms.DateInput(attrs={'class': 'cf-input', 'type': 'date', 'required': 'required'}),
            'status': forms.Select(attrs={'class': 'cf-select'}),
        }


class CreateCalendarEventForm(forms.ModelForm):
    """Creates a calendar event (audit visit, IRD hearing, meeting) for a client."""
    class Meta:
        from calendar_app.models import CalendarEvent
        model = CalendarEvent
        fields = ['title', 'event_type', 'start_time', 'end_time', 'is_all_day', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. FY 2080/81 Final Audit Review / Tax Hearing',
                'required': 'required',
            }),
            'event_type': forms.Select(attrs={'class': 'cf-select'}),
            'start_time': forms.DateTimeInput(attrs={'class': 'cf-input', 'type': 'datetime-local', 'required': 'required'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'cf-input', 'type': 'datetime-local', 'required': 'required'}),
            'is_all_day': forms.CheckboxInput(attrs={'class': 'cf-checkbox'}),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 3,
                'placeholder': 'Meeting agenda, location, audit scope, or hearing notes...',
            }),
        }

