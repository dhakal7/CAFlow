from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import User
from clients.constants import SERVICE_CHOICES
from clients.models import Client
from firms.models import FirmMembership, MembershipStatus
from tasks.models import (
    Task,
    TaskAttachment,
    TaskChecklistItem,
    TaskComment,
    WorkflowTemplate,
)


class TaskForm(forms.ModelForm):
    """
    Form for creating and editing tasks with full Nepal CA practice scoping.
    """
    service = forms.ChoiceField(
        choices=[('', _('-- Select Accounting Service --'))] + list(SERVICE_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'cf-select'}),
        label=_('Service / Engagement Type'),
    )
    template_id = forms.ChoiceField(
        choices=[('', _('-- Select Workflow Template (Optional) --'))],
        required=False,
        widget=forms.Select(attrs={'class': 'cf-select', 'id': 'task-template-select'}),
        label=_('Apply Workflow Template'),
        help_text=_('Pre-populates checklist items and service presets.'),
    )
    checklist_raw = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_checklist_raw'}),
    )

    class Meta:
        model = Task
        fields = [
            'title',
            'description',
            'client',
            'service',
            'category',
            'assigned_to',
            'priority',
            'start_date',
            'due_date',
            'estimated_hours',
            'status',
            'is_recurring',
            'recurrence_interval',
            'custom_recurrence_days',
            'recurrence_end_date',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Monthly VAT Return Filing - Ashoj 2081',
                'required': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 3,
                'placeholder': 'Add task instructions, specific IRD references, or audit checklist notes...',
            }),
            'client': forms.Select(attrs={'class': 'cf-select'}),
            'category': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Tax Compliance, Audit, Advisory',
            }),
            'assigned_to': forms.Select(attrs={'class': 'cf-select'}),
            'priority': forms.Select(attrs={'class': 'cf-select'}),
            'status': forms.Select(attrs={'class': 'cf-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. 8.0',
                'step': '0.5',
                'min': '0',
            }),
            'is_recurring': forms.CheckboxInput(attrs={
                'class': 'cf-checkbox',
                'id': 'id_is_recurring',
            }),
            'recurrence_interval': forms.Select(attrs={
                'class': 'cf-select',
                'id': 'id_recurrence_interval',
            }),
            'custom_recurrence_days': forms.NumberInput(attrs={
                'class': 'cf-input',
                'placeholder': 'Days (e.g. 15)',
                'min': '1',
            }),
            'recurrence_end_date': forms.DateInput(attrs={
                'class': 'cf-input',
                'type': 'date',
            }),
        }

    def __init__(self, *args, **kwargs):
        firm = kwargs.pop('firm', None)
        super().__init__(*args, **kwargs)

        if firm:
            # Scope clients to active firm
            self.fields['client'].queryset = Client.objects.filter(
                firm=firm,
                is_active=True,
            ).order_by('business_name', 'name')
            self.fields['client'].empty_label = _('-- Select Client Entity --')

            # Scope staff to active firm members
            active_memberships = FirmMembership.objects.filter(
                firm=firm,
                status=MembershipStatus.ACTIVE,
            ).select_related('user')
            user_ids = [m.user_id for m in active_memberships]
            self.fields['assigned_to'].queryset = User.objects.filter(
                id__in=user_ids,
                is_active=True,
            ).order_by('first_name', 'last_name')
            self.fields['assigned_to'].empty_label = _('-- Unassigned / Open Pool --')

            # Populate templates
            templates = WorkflowTemplate.objects.filter(
                firm=firm,
                is_active=True,
            ).order_by('title')
            self.fields['template_id'].choices = [('', _('-- Select Workflow Template (Optional) --'))] + [
                (str(t.id), f"{t.title} ({t.items.count()} steps)") for t in templates
            ]


class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 3,
                'placeholder': 'Write an internal note or review feedback...',
                'required': True,
            }),
        }


class TaskAttachmentForm(forms.ModelForm):
    class Meta:
        model = TaskAttachment
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={
                'class': 'cf-input',
                'required': True,
            }),
        }


class TaskChecklistItemForm(forms.ModelForm):
    class Meta:
        model = TaskChecklistItem
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'Add a step (e.g. Verify sales vouchers against IRD ledger)...',
                'required': True,
            }),
        }


class WorkflowTemplateForm(forms.ModelForm):
    checklist_lines = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'cf-input',
            'rows': 6,
            'placeholder': 'Enter each checklist step on a new line, e.g.:\nRequest documents\nReceive sales data\nReceive purchase data\nReview documents\nPrepare working papers\nCA review\nFinalize\nNotify client',
            'required': True,
        }),
        label=_('Checklist Steps (One per line)'),
        help_text=_('Each line will become a discrete checklist item.'),
    )

    class Meta:
        model = WorkflowTemplate
        fields = [
            'title',
            'description',
            'service',
            'default_priority',
            'estimated_days',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'cf-input',
                'placeholder': 'e.g. Monthly VAT Workflow',
                'required': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'cf-input',
                'rows': 2,
                'placeholder': 'Brief description of standard procedure...',
            }),
            'service': forms.Select(
                choices=[('', _('-- General / All Services --'))] + list(SERVICE_CHOICES),
                attrs={'class': 'cf-select'},
            ),
            'default_priority': forms.Select(
                choices=Task.Priority.choices,
                attrs={'class': 'cf-select'},
            ),
            'estimated_days': forms.NumberInput(attrs={
                'class': 'cf-input',
                'min': '1',
            }),
        }
