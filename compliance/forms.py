from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from clients.models import Client
from documents.models import Document
from firms.models import FirmMembership, MembershipStatus
from tasks.models import Task
from compliance.models import (
    ComplianceDeadline,
    ComplianceType,
    ClientComplianceRequirement,
)


class ComplianceDeadlineForm(forms.ModelForm):
    """
    Form for creating and editing compliance deadlines.
    Strictly scoped to active firm workspace.
    """
    class Meta:
        model = ComplianceDeadline
        fields = [
            'title',
            'client',
            'compliance_type',
            'governing_act',
            'description',
            'period',
            'due_date_bs',
            'due_date_ad',
            'assigned_to',
            'reviewer',
            'priority',
            'status',
            'notes',
            'filing_reference_number',
            'completion_date',
            'is_recurring',
            'recurrence_frequency',
            'recurrence_end_date',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Monthly VAT Return (Bhadra 2081)',
                'required': True,
            }),
            'client': forms.Select(attrs={'class': 'cf-select'}),
            'compliance_type': forms.Select(attrs={'class': 'cf-select'}),
            'governing_act': forms.Select(attrs={'class': 'cf-select'}),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
                'placeholder': 'Filing scope, Annex requirements, portal guidelines...',
            }),
            'period': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Bhadra 2081, Q1 2081/82, Ashoj 2081',
            }),
            'due_date_bs': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. 2081-06-25',
                'required': True,
            }),
            'due_date_ad': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
                'required': True,
            }),
            'assigned_to': forms.Select(attrs={'class': 'cf-select'}),
            'reviewer': forms.Select(attrs={'class': 'cf-select'}),
            'priority': forms.Select(attrs={'class': 'cf-select'}),
            'status': forms.Select(attrs={'class': 'cf-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
                'placeholder': 'Statutory penalty provisions, working paper notes...',
            }),
            'filing_reference_number': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. IRD Token / SSF Receipt / OCR Reg #',
            }),
            'completion_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
            }),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'cf-checkbox'}),
            'recurrence_frequency': forms.Select(attrs={'class': 'cf-select'}),
            'recurrence_end_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
            }),
        }

    def __init__(self, *args, **kwargs):
        firm = kwargs.pop('firm', None)
        super().__init__(*args, **kwargs)

        if firm:
            # Scope clients
            self.fields['client'].queryset = Client.objects.filter(
                firm=firm,
                is_active=True,
            ).order_by('business_name', 'name')
            self.fields['client'].empty_label = _('-- Select Client Entity (or General Firm Deadline) --')

            # Scope configurable compliance types
            self.fields['compliance_type'].queryset = ComplianceType.objects.filter(
                firm=firm,
                is_active=True,
            ).order_by('category', 'name')
            self.fields['compliance_type'].empty_label = _('-- Custom / Non-standard Type --')

            # Scope active staff members
            active_memberships = FirmMembership.objects.filter(
                firm=firm,
                status=MembershipStatus.ACTIVE,
                is_active=True,
            ).select_related('user')
            user_ids = [m.user_id for m in active_memberships]
            active_users_qs = User.objects.filter(id__in=user_ids).order_by('first_name', 'last_name')

            self.fields['assigned_to'].queryset = active_users_qs
            self.fields['assigned_to'].empty_label = _('-- Select Assigned Staff --')

            self.fields['reviewer'].queryset = active_users_qs
            self.fields['reviewer'].empty_label = _('-- Select Reviewer / Partner --')


class ComplianceTypeForm(forms.ModelForm):
    """
    Form for creating and editing configurable statutory compliance types.
    """
    class Meta:
        model = ComplianceType
        fields = [
            'name',
            'code',
            'category',
            'statutory_authority',
            'frequency',
            'default_priority',
            'due_day_bs',
            'description',
            'penalty_guidelines',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Monthly VAT Return & E-Filing',
                'required': True,
            }),
            'code': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. VAT_MONTHLY',
            }),
            'category': forms.Select(attrs={'class': 'cf-select'}),
            'statutory_authority': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Inland Revenue Department (IRD)',
            }),
            'frequency': forms.Select(attrs={'class': 'cf-select'}),
            'default_priority': forms.Select(attrs={'class': 'cf-select'}),
            'due_day_bs': forms.NumberInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. 25',
                'min': '1',
                'max': '32',
            }),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 3,
                'placeholder': 'Details and filing instructions...',
            }),
            'penalty_guidelines': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
                'placeholder': 'Statutory fines, interest rates, Section citations...',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'cf-checkbox'}),
        }


class ClientComplianceRequirementForm(forms.ModelForm):
    """
    Form to assign a compliance requirement to a client entity.
    """
    class Meta:
        model = ClientComplianceRequirement
        fields = [
            'client',
            'compliance_type',
            'frequency',
            'assigned_staff',
            'reviewer',
            'notes',
            'is_active',
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'cf-select'}),
            'compliance_type': forms.Select(attrs={'class': 'cf-select'}),
            'frequency': forms.Select(attrs={'class': 'cf-select'}),
            'assigned_staff': forms.Select(attrs={'class': 'cf-select'}),
            'reviewer': forms.Select(attrs={'class': 'cf-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
                'placeholder': 'Portal login reference, client-specific exemption notes...',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'cf-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        firm = kwargs.pop('firm', None)
        super().__init__(*args, **kwargs)
        if firm:
            self.fields['client'].queryset = Client.objects.filter(firm=firm, is_active=True).order_by('business_name', 'name')
            self.fields['compliance_type'].queryset = ComplianceType.objects.filter(firm=firm, is_active=True).order_by('category', 'name')

            active_memberships = FirmMembership.objects.filter(
                firm=firm,
                status=MembershipStatus.ACTIVE,
                is_active=True,
            )
            user_ids = [m.user_id for m in active_memberships]
            users_qs = User.objects.filter(id__in=user_ids).order_by('first_name', 'last_name')
            self.fields['assigned_staff'].queryset = users_qs
            self.fields['reviewer'].queryset = users_qs


class ComplianceStatusTransitionForm(forms.Form):
    """
    Handles workflow status transitions with optional notes and reference number.
    """
    status = forms.ChoiceField(
        choices=ComplianceDeadline.Status.choices,
        widget=forms.Select(attrs={'class': 'cf-select'}),
    )
    filing_reference_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'cf-input',
            'placeholder': 'IRD Token / Payment Challan / Ack Reference',
        }),
    )
    completion_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'cf-input', 'type': 'date'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'cf-input',
            'rows': 2,
            'placeholder': 'Reason for status update, reviewer comments, or remarks...',
        }),
    )


class LinkTaskForm(forms.Form):
    """
    Connect an existing task or create a new task linked to a compliance deadline.
    """
    existing_task_id = forms.UUIDField(
        required=False,
        widget=forms.Select(attrs={'class': 'cf-select'}),
    )
    new_task_title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'cf-input',
            'placeholder': 'Or create new task title (e.g. Prepare VAT Working Papers)',
        }),
    )

    def __init__(self, *args, **kwargs):
        firm = kwargs.pop('firm', None)
        client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
        if firm:
            qs = Task.objects.filter(firm=firm).exclude(status=Task.Status.COMPLETED)
            if client:
                qs = qs.filter(client=client)
            self.fields['existing_task_id'].widget.choices = [
                ('', _('-- Select Existing Task --'))
            ] + [(str(t.id), f"{t.title} ({t.get_status_display()})") for t in qs[:50]]


class LinkDocumentForm(forms.Form):
    """
    Connect an existing client document or upload a new one for this compliance filing.
    """
    existing_document_id = forms.UUIDField(
        required=False,
        widget=forms.Select(attrs={'class': 'cf-select'}),
    )
    upload_file = forms.FileField(required=False)
    document_title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'cf-input',
            'placeholder': 'Document title (if uploading)',
        }),
    )

    def __init__(self, *args, **kwargs):
        firm = kwargs.pop('firm', None)
        client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
        if firm:
            qs = Document.objects.filter(firm=firm)
            if client:
                qs = qs.filter(client=client)
            self.fields['existing_document_id'].widget.choices = [
                ('', _('-- Select Existing Document --'))
            ] + [(str(d.id), f"{d.title} ({d.get_category_display()})") for d in qs[:50]]
