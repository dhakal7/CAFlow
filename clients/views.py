import csv
import json
from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView, DetailView

from accounts.models import User
from audit.models import AuditLog
from audit.services import log_audit
from billing.models import Invoice
from clients.constants import (
    BUSINESS_TYPE_CHOICES,
    FISCAL_YEAR_CHOICES,
    SERVICE_CHOICES,
    SERVICE_DICT,
)
from clients.forms import (
    AssignStaffForm,
    ClientForm,
    CreateCalendarEventForm,
    CreateClientTaskForm,
    CreateInvoiceForm,
    RequestDocumentForm,
    SendMessageForm,
    UploadDocumentForm,
)
from clients.models import Client, ClientActivity
from compliance.models import (
    ComplianceDeadline,
    ComplianceType,
    ClientComplianceRequirement,
)
from calendar_app.models import CalendarEvent
from documents.models import Document, DocumentRequest
from firms.mixins import FirmRequiredMixin, PermissionRequiredMixin
from firms.models import MembershipStatus
from messages_app.models import ChatMessage, Conversation
from tasks.models import Task


def get_firm_client_or_404(request, client_id):
    """
    Enforces strict 3-tier tenant isolation:
    User -> Firm -> Client.
    Never trusts URL IDs alone.
    """
    if not request.user.is_authenticated:
        raise PermissionDenied(_("User authentication required."))
    firm = getattr(request, 'firm', None)
    if not firm:
        raise PermissionDenied(_("Active firm workspace required."))
    has_membership = request.user.firm_memberships.filter(
        firm=firm,
        status=MembershipStatus.ACTIVE,
        is_active=True,
    ).exists()
    if not has_membership:
        raise PermissionDenied(_("User is not an active member of this firm."))
    return get_object_or_404(Client.objects.filter(firm=firm), id=client_id)


def redirect_after_action(request, client):
    """
    Redirects back to source page (detail page or list page) after modal action.
    Validates redirect target against open redirect attacks.
    """
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        return redirect(next_url)
    referer = request.META.get('HTTP_REFERER')
    if referer and str(client.id) in referer:
        return redirect('clients:client_detail', client_id=client.id)
    return redirect('clients:client_list')




class ClientListView(PermissionRequiredMixin, ListView):
    """
    Production-ready Client CRM Directory.
    Strictly tenant-scoped with multi-criteria filtering, search, pagination, and quick actions.
    """
    firm_permission = 'view_client'
    model = Client

    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 15

    def get_queryset(self):
        firm = self.request.firm
        qs = Client.objects.filter(firm=firm).select_related('assigned_manager').prefetch_related(
            'assigned_staff', 'compliance_deadlines', 'tasks'
        )

        # 1. Global Search
        search_query = self.request.GET.get('q', '').strip()
        if search_query:
            qs = qs.filter(
                Q(name__icontains=search_query) |
                Q(business_name__icontains=search_query) |
                Q(legal_name__icontains=search_query) |
                Q(pan_number__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(phone__icontains=search_query) |
                Q(contact_person__icontains=search_query)
            )

        # 2. Status Filter
        status_filter = self.request.GET.get('status', '').strip().upper()
        if status_filter:
            if status_filter == 'ACTIVE':
                qs = qs.filter(status=Client.Status.ACTIVE)
            elif status_filter == 'ONBOARDING':
                qs = qs.filter(status=Client.Status.ONBOARDING)
            elif status_filter == 'ARCHIVED':
                qs = qs.filter(status=Client.Status.ARCHIVED)
            elif status_filter == 'SUSPENDED':
                qs = qs.filter(status=Client.Status.SUSPENDED)
            elif status_filter == 'INACTIVE':
                qs = qs.filter(status__in=[Client.Status.INACTIVE, Client.Status.SUSPENDED, Client.Status.ARCHIVED])

        # 3. Service Filter
        service_filter = self.request.GET.get('service', '').strip()
        if service_filter:
            qs = qs.filter(services__contains=service_filter)

        # 4. Assigned Staff Filter
        staff_filter = (self.request.GET.get('assigned_to', '') or self.request.GET.get('manager', '')).strip()
        if staff_filter:
            qs = qs.filter(
                Q(assigned_manager_id=staff_filter) |
                Q(assigned_staff__id=staff_filter)
            ).distinct()

        # 5. Business Type Filter
        type_filter = (self.request.GET.get('client_type', '') or self.request.GET.get('type', '')).strip()
        if type_filter:
            qs = qs.filter(client_type=type_filter)

        # 6. Upcoming Deadline Filter
        deadline_filter = self.request.GET.get('deadline', '').strip()
        today = timezone.localdate()
        if deadline_filter == 'overdue':
            qs = qs.filter(
                Q(compliance_deadlines__due_date_ad__lt=today, compliance_deadlines__status__in=['UPCOMING', 'DUE_SOON', 'OVERDUE']) |
                Q(tasks__due_date__lt=today, tasks__status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS])
            ).distinct()
        elif deadline_filter == '7days':
            next_week = today + timedelta(days=7)
            qs = qs.filter(
                Q(compliance_deadlines__due_date_ad__gte=today, compliance_deadlines__due_date_ad__lte=next_week) |
                Q(tasks__due_date__gte=today, tasks__due_date__lte=next_week)
            ).distinct()
        elif deadline_filter == '30days':
            next_month = today + timedelta(days=30)
            qs = qs.filter(
                Q(compliance_deadlines__due_date_ad__gte=today, compliance_deadlines__due_date_ad__lte=next_month) |
                Q(tasks__due_date__gte=today, tasks__due_date__lte=next_month)
            ).distinct()

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm

        # Total counts for statistics
        base_firm_clients = Client.objects.filter(firm=firm)
        context['total_count'] = base_firm_clients.count()
        context['active_count'] = base_firm_clients.filter(status=Client.Status.ACTIVE).count()
        context['onboarding_count'] = base_firm_clients.filter(status=Client.Status.ONBOARDING).count()
        context['inactive_count'] = base_firm_clients.filter(
            status__in=[Client.Status.INACTIVE, Client.Status.SUSPENDED, Client.Status.ARCHIVED]
        ).count()
        context['archived_count'] = base_firm_clients.filter(status=Client.Status.ARCHIVED).count()

        # Team members for assignment and filter options
        context['team_members'] = User.objects.filter(
            firm_memberships__firm=firm,
            firm_memberships__status=MembershipStatus.ACTIVE,
            is_active=True,
        ).distinct().order_by('first_name', 'last_name')

        # Dropdown options
        context['service_choices'] = SERVICE_CHOICES
        context['business_type_choices'] = BUSINESS_TYPE_CHOICES
        context['fiscal_year_choices'] = FISCAL_YEAR_CHOICES
        context['breadcrumbs'] = [
            {'title': 'Clients', 'url': ''},
        ]

        # Forms for modals
        context['client_form'] = ClientForm(firm=firm)
        context['assign_staff_form'] = AssignStaffForm(firm=firm)
        context['document_request_form'] = RequestDocumentForm()
        context['task_form'] = CreateClientTaskForm(firm=firm)
        context['message_form'] = SendMessageForm()

        # Query filters active status
        q = self.request.GET.get('q', '')
        status = self.request.GET.get('status', '')
        service = self.request.GET.get('service', '')
        assigned_to = self.request.GET.get('assigned_to', '')
        client_type = self.request.GET.get('client_type', '')
        deadline = self.request.GET.get('deadline', '')

        active_filters_count = sum(1 for v in [status, service, assigned_to, client_type, deadline] if v)
        context['active_filters_count'] = active_filters_count
        context['current_q'] = q
        context['current_status'] = status
        context['current_service'] = service
        context['current_assigned_to'] = assigned_to
        context['current_client_type'] = client_type
        context['current_deadline'] = deadline
        context['has_filters'] = bool(q or active_filters_count > 0)

        return context


class ClientDetailJsonView(PermissionRequiredMixin, View):
    """
    Returns full details of a client entity as JSON for the slide-over inspection drawer.
    Strictly tenant-scoped.
    """
    firm_permission = 'view_client'

    def get(self, request, client_id):

        client = get_object_or_404(Client.objects.filter(firm=request.firm), id=client_id)

        # Team
        manager_data = None
        if client.assigned_manager:
            manager_data = {
                'id': str(client.assigned_manager.id),
                'name': client.assigned_manager.get_full_name() or client.assigned_manager.email,
                'email': client.assigned_manager.email,
                'initials': client.assigned_manager.first_name[:1] + client.assigned_manager.last_name[:1] if client.assigned_manager.first_name else 'CA',
            }

        staff_list = [
            {
                'id': str(u.id),
                'name': u.get_full_name() or u.email,
                'email': u.email,
            }
            for u in client.assigned_staff.all()
        ]

        # Services
        services_list = [
            {'code': s, 'name': SERVICE_DICT.get(s, s)}
            for s in (client.services or [])
        ]

        # Upcoming Deadlines
        today = timezone.localdate()
        deadlines = [
            {
                'title': d.title,
                'due_date_ad': str(d.due_date_ad),
                'due_date_bs': d.due_date_bs,
                'status': d.get_status_display(),
                'days_left': (d.due_date_ad - today).days,
            }
            for d in client.compliance_deadlines.filter(due_date_ad__gte=today).order_by('due_date_ad')[:5]
        ]

        # Active Tasks
        tasks = [
            {
                'id': str(t.id),
                'title': t.title,
                'status': t.get_status_display(),
                'priority': t.get_priority_display(),
                'due_date': str(t.due_date) if t.due_date else 'No Date',
                'assigned_to': t.assigned_to.get_full_name() if t.assigned_to else 'Unassigned',
            }
            for t in client.tasks.exclude(status=Task.Status.COMPLETED).order_by('due_date')[:5]
        ]

        # Recent Document Requests
        doc_requests = [
            {
                'documents': r.requested_documents,
                'due_date': str(r.due_date),
                'status': r.get_status_display(),
            }
            for r in client.document_requests.all().order_by('-created_at')[:4]
        ]

        # Activities
        activities = [
            {
                'activity_type': a.get_activity_type_display(),
                'description': a.description,
                'performed_by': a.performed_by.get_full_name() if a.performed_by else 'System',
                'created_at': a.created_at.strftime('%b %d, %Y %H:%M'),
            }
            for a in client.activities.all().order_by('-created_at')[:6]
        ]

        data = {
            'id': str(client.id),
            'name': client.name,
            'legal_name': client.legal_name or client.display_business_name,
            'business_name': client.display_business_name,
            'pan_number': client.pan_number or 'N/A',
            'registration_number': client.registration_number or 'N/A',
            'registration_date': str(client.registration_date) if client.registration_date else 'N/A',
            'tax_registration_date': str(client.tax_registration_date) if client.tax_registration_date else 'N/A',
            'notes': client.notes or '',
            'client_type': client.get_client_type_display(),
            'client_type_code': client.client_type,
            'contact_person': client.contact_person or client.name,
            'email': client.email or 'N/A',
            'phone': client.phone or 'N/A',
            'address': client.address or 'N/A',
            'city': client.city,
            'fiscal_year': client.fiscal_year,
            'status': client.status,
            'status_display': client.get_status_display(),
            'assigned_manager': manager_data,
            'assigned_staff': staff_list,
            'services': services_list,
            'deadlines': deadlines,
            'tasks': tasks,
            'document_requests': doc_requests,
            'activities': activities,
        }

        # Log viewing audit entry
        log_audit(
            request=request,
            action=AuditLog.ActionType.VIEW,
            object_type='Client',
            object_id=str(client.id),
            description=f"Viewed client profile: {client.display_business_name} (PAN: {client.pan_number})",
        )

        return JsonResponse(data)


class ClientCreateView(PermissionRequiredMixin, View):
    """
    Creates a new client associated with the active firm.
    Supports multi-step submissions, staff assignment, onboarding task creation, and audit logging.
    """
    firm_permission = 'create_client'

    def post(self, request):
        form = ClientForm(request.POST, firm=request.firm)
        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Please correct the errors in the form.'))
            return redirect('clients:client_list')

        client = form.save(commit=False)
        client.firm = request.firm
        client.services = form.cleaned_data.get('services', [])
        client.save()

        # Assign ManyToMany staff
        assigned_staff_users = form.cleaned_data.get('assigned_staff')
        if assigned_staff_users:
            client.assigned_staff.set(assigned_staff_users)

        # 1. Auto-generate onboarding tasks if requested
        if form.cleaned_data.get('create_onboarding_tasks'):
            lead_user = client.assigned_manager or request.user
            today = timezone.localdate()
            onboarding_tasks = [
                (
                    f"Collect PAN Certificate, OCR Registration & MOA/AOA: {client.display_business_name}",
                    "Collect certified copies of OCR Registration, IRD PAN Certificate, Articles of Association, and Shareholder Register.",
                    Task.Priority.HIGH,
                    today + timedelta(days=3),
                ),
                (
                    f"Verify IRD Tax Clearance & Prior Year Returns: {client.display_business_name}",
                    "Review previous year audited financials, tax assessment order, and advance tax payments from IRD portal.",
                    Task.Priority.MEDIUM,
                    today + timedelta(days=7),
                ),
                (
                    f"Execute CA Engagement Letter & KYC Verification: {client.display_business_name}",
                    "Draft formal engagement contract specifying scope of audit/tax services, fee structure, and obtain Director KYC documentation.",
                    Task.Priority.HIGH,
                    today + timedelta(days=5),
                ),
            ]
            for title, desc, prio, due in onboarding_tasks:
                Task.objects.create(
                    firm=request.firm,
                    client=client,
                    title=title,
                    description=desc,
                    assigned_to=lead_user,
                    priority=prio,
                    status=Task.Status.TODO,
                    due_date=due,
                )

        # 2. Create timeline activity
        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.NEW_CLIENT,
            description=f"Client '{client.display_business_name}' registered under PAN {client.pan_number or 'N/A'}.",
            performed_by=request.user,
        )

        # 3. Create Audit Log
        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='Client',
            object_id=str(client.id),
            description=f"Registered new client: {client.display_business_name} (PAN: {client.pan_number}) with status {client.get_status_display()}.",
        )

        msg = _(f"Client '{client.display_business_name}' has been successfully onboarded.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'client_id': str(client.id), 'message': msg})

        messages.success(request, msg)
        return redirect('clients:client_list')


class ClientEditView(PermissionRequiredMixin, View):
    """
    Updates client details. Strictly tenant scoped (User -> Firm -> Client).
    """
    firm_permission = 'edit_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = ClientForm(request.POST, instance=client, firm=request.firm)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Could not update client. Please check entered values.'))
            return redirect_after_action(request, client)

        updated_client = form.save(commit=False)
        updated_client.services = form.cleaned_data.get('services', [])
        updated_client.save()

        assigned_staff_users = form.cleaned_data.get('assigned_staff')
        if assigned_staff_users is not None:
            updated_client.assigned_staff.set(assigned_staff_users)

        # Record activity & audit log
        ClientActivity.objects.create(
            firm=request.firm,
            client=updated_client,
            activity_type=ClientActivity.ActivityType.STATUS_CHANGED,
            description=f"Client profile information updated by {request.user.get_full_name()}.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Client',
            object_id=str(updated_client.id),
            description=f"Updated details for client: {updated_client.display_business_name}.",
        )

        msg = _(f"Details for '{updated_client.display_business_name}' successfully updated.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, updated_client)


class ClientAssignStaffView(PermissionRequiredMixin, View):
    """
    Assigns Engagement Manager and Staff members to a client.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'edit_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = AssignStaffForm(request.POST, firm=request.firm)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Invalid team assignment.'))
            return redirect_after_action(request, client)

        manager = form.cleaned_data.get('assigned_manager')
        staff_users = form.cleaned_data.get('assigned_staff')

        client.assigned_manager = manager
        client.save(update_fields=['assigned_manager'])
        if staff_users is not None:
            client.assigned_staff.set(staff_users)

        lead_name = manager.get_full_name() if manager else "None"
        total_staff_count = staff_users.count() if staff_users else 0
        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.STAFF_ASSIGNED,
            description=f"Assigned lead manager: {lead_name} and {total_staff_count} associate(s).",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Client',
            object_id=str(client.id),
            description=f"Updated engagement team assignment for {client.display_business_name}: Lead={lead_name}.",
        )

        msg = _(f"Engagement team successfully updated for '{client.display_business_name}'.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientRequestDocumentView(PermissionRequiredMixin, View):
    """
    Creates a new DocumentRequest for a client.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'request_document'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = RequestDocumentForm(request.POST)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Could not create document request.'))
            return redirect_after_action(request, client)

        doc_req = form.save(commit=False)
        doc_req.firm = request.firm
        doc_req.client = client
        doc_req.requested_by = request.user
        doc_req.save()

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.DOC_REQUESTED,
            description=f"Requested documents: '{doc_req.requested_documents}' due by {doc_req.due_date}.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='DocumentRequest',
            object_id=str(doc_req.id),
            description=f"Sent document request to {client.display_business_name}: {doc_req.requested_documents}.",
        )

        msg = _(f"Document request sent to '{client.display_business_name}'.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientCreateTaskView(PermissionRequiredMixin, View):
    """
    Creates an engagement task tied to a specific client.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'create_task'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = CreateClientTaskForm(request.POST, firm=request.firm)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Could not create task. Please check form values.'))
            return redirect_after_action(request, client)

        task = form.save(commit=False)
        task.firm = request.firm
        task.client = client
        task.save()

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.TASK_CREATED,
            description=f"Created task: '{task.title}' assigned to {task.assigned_to.get_full_name() if task.assigned_to else 'Unassigned'}.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='Task',
            object_id=str(task.id),
            description=f"Created task for client {client.display_business_name}: {task.title}.",
        )

        msg = _(f"Task '{task.title}' successfully assigned.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientSendMessageView(PermissionRequiredMixin, View):
    """
    Sends a message / creates a conversation thread with client context.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'view_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = SendMessageForm(request.POST)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Please supply both subject and message text.'))
            return redirect_after_action(request, client)

        subject = form.cleaned_data['subject']
        body = form.cleaned_data['body']

        conversation = Conversation.objects.create(
            firm=request.firm,
            client=client,
            title=subject,
        )
        conversation.participants.add(request.user)
        if client.assigned_manager and client.assigned_manager != request.user:
            conversation.participants.add(client.assigned_manager)

        ChatMessage.objects.create(
            firm=request.firm,
            conversation=conversation,
            sender=request.user,
            body=body,
        )

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.MESSAGE_RECEIVED,
            description=f"Dispatched message: '{subject}'.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='ChatMessage',
            object_id=str(conversation.id),
            description=f"Dispatched message regarding {client.display_business_name}: {subject}.",
        )

        msg = _(f"Message sent to client thread for '{client.display_business_name}'.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientToggleStatusView(PermissionRequiredMixin, View):
    """
    Deactivates, archives, or re-activates a client entity.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'edit_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        action = request.POST.get('action', '').strip().lower()

        if action == 'archive':
            client.status = Client.Status.ARCHIVED
            client.is_active = False
            action_desc = "Archived client entity."
            status_label = "Archived"
            act_type = ClientActivity.ActivityType.CLIENT_ARCHIVED
        elif action == 'restore':
            client.status = Client.Status.ACTIVE
            client.is_active = True
            action_desc = "Restored client entity."
            status_label = "Active"
            act_type = ClientActivity.ActivityType.CLIENT_RESTORED
        elif client.status in [Client.Status.ACTIVE, Client.Status.ONBOARDING]:
            client.status = Client.Status.INACTIVE
            client.is_active = False
            action_desc = "Deactivated client entity."
            status_label = "Inactive"
            act_type = ClientActivity.ActivityType.STATUS_CHANGED
        else:
            client.status = Client.Status.ACTIVE
            client.is_active = True
            action_desc = "Re-activated client entity."
            status_label = "Active"
            act_type = ClientActivity.ActivityType.CLIENT_RESTORED if client.status == Client.Status.ARCHIVED else ClientActivity.ActivityType.STATUS_CHANGED

        client.save(update_fields=['status', 'is_active'])

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=act_type,
            description=f"{action_desc} Set status to {status_label}.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Client',
            object_id=str(client.id),
            description=f"{action_desc} Client: {client.display_business_name} (New Status: {status_label}).",
        )

        msg = _(f"Client '{client.display_business_name}' status changed to {status_label}.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'status': client.status, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientArchiveView(PermissionRequiredMixin, View):
    """
    Archives a client entity.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'edit_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        client.status = Client.Status.ARCHIVED
        client.is_active = False
        client.save(update_fields=['status', 'is_active'])

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.CLIENT_ARCHIVED,
            description=f"Client '{client.display_business_name}' has been archived.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Client',
            object_id=str(client.id),
            description=f"Archived client: {client.display_business_name}.",
        )

        msg = _(f"Client '{client.display_business_name}' has been archived.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'status': client.status, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientRestoreView(PermissionRequiredMixin, View):
    """
    Restores an archived or inactive client entity to active status.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'edit_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        client.status = Client.Status.ACTIVE
        client.is_active = True
        client.save(update_fields=['status', 'is_active'])

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.CLIENT_RESTORED,
            description=f"Client '{client.display_business_name}' has been restored to active status.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Client',
            object_id=str(client.id),
            description=f"Restored client: {client.display_business_name}.",
        )

        msg = _(f"Client '{client.display_business_name}' has been restored to active status.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'status': client.status, 'message': msg})

        messages.success(request, msg)
        return redirect_after_action(request, client)


class ClientCreateCalendarEventView(PermissionRequiredMixin, View):
    """
    Creates a calendar event (audit visit, tax hearing, client review meeting) for the client.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'edit_client'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = CreateCalendarEventForm(request.POST)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Could not schedule event. Please check form inputs.'))
            return redirect_after_action(request, client)

        event = form.save(commit=False)
        event.firm = request.firm
        event.client = client
        event.created_by = request.user
        event.save()

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.STATUS_CHANGED,
            description=f"Scheduled {event.get_event_type_display()}: '{event.title}'.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='CalendarEvent',
            object_id=str(event.id),
            description=f"Scheduled calendar event for {client.display_business_name}: {event.title}.",
        )

        msg = _(f"Calendar event '{event.title}' successfully scheduled.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect(f"/clients/{client.id}/?tab=calendar")



class ClientExportView(PermissionRequiredMixin, View):
    """
    Exports client registry to CSV with UTF-8 BOM encoding for Excel.
    Respects current filter criteria and records audit log.
    """
    firm_permission = 'view_client'

    def get(self, request):
        firm = request.firm
        qs = Client.objects.filter(firm=firm).select_related('assigned_manager').order_by('name')

        # Apply search and filters if passed
        search_query = request.GET.get('q', '').strip()
        if search_query:
            qs = qs.filter(
                Q(name__icontains=search_query) |
                Q(business_name__icontains=search_query) |
                Q(legal_name__icontains=search_query) |
                Q(pan_number__icontains=search_query)
            )

        status_filter = request.GET.get('status', '').strip().upper()
        if status_filter:
            if status_filter == 'ACTIVE':
                qs = qs.filter(status=Client.Status.ACTIVE)
            elif status_filter == 'ONBOARDING':
                qs = qs.filter(status=Client.Status.ONBOARDING)
            elif status_filter == 'ARCHIVED':
                qs = qs.filter(status=Client.Status.ARCHIVED)
            elif status_filter == 'SUSPENDED':
                qs = qs.filter(status=Client.Status.SUSPENDED)
            elif status_filter == 'INACTIVE':
                qs = qs.filter(status__in=[Client.Status.INACTIVE, Client.Status.SUSPENDED, Client.Status.ARCHIVED])

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f"CAFlow_Clients_{firm.slug}_{timezone.localdate()}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Client Contact',
            'Legal / Registered Name',
            'Business / Entity Name',
            'IRD PAN Number',
            'Business Type',
            'Fiscal Year',
            'Primary Email',
            'Phone',
            'Registered Address',
            'City / District',
            'Status',
            'Engagement Lead',
            'Subscribed Services',
            'Created Date',
        ])

        count = 0
        for c in qs:
            services_str = ", ".join(c.services_display)
            lead_str = c.assigned_manager.get_full_name() if c.assigned_manager else "Unassigned"
            writer.writerow([
                c.display_contact_name,
                c.legal_name or c.display_business_name,
                c.display_business_name,
                c.pan_number,
                c.get_client_type_display(),
                c.fiscal_year,
                c.email,
                c.phone,
                c.address,
                c.city,
                c.get_status_display(),
                lead_str,
                services_str,
                c.created_at.strftime('%Y-%m-%d'),
            ])
            count += 1

        log_audit(
            request=request,
            action=AuditLog.ActionType.EXPORT,
            object_type='Client',
            description=f"Exported client registry CSV: {count} records.",
        )

        return response


class ClientDetailView(PermissionRequiredMixin, View):
    """
    Production-grade Client Detail Page at /clients/<id>/.
    Enforces strict 3-tier tenant isolation (User -> Firm -> Client) before every operation.
    """
    firm_permission = 'view_client'
    template_name = 'clients/client_detail.html'

    def get(self, request, client_id):

        # Strict tenant verification: User -> Firm -> Client
        client = get_firm_client_or_404(request, client_id)
        active_tab = request.GET.get('tab', 'overview').lower()

        # Audit log viewing
        log_audit(
            request=request,
            action=AuditLog.ActionType.VIEW,
            object_type='Client',
            object_id=str(client.id),
            description=f"Viewed full client profile: {client.display_business_name} (PAN: {client.pan_number}).",
        )

        today = timezone.localdate()

        # 1. Team categorized by 4 practice tiers: CA, Senior, Accountant, Staff
        team_by_role = client.get_assigned_team_by_role()

        # 2. Services data
        service_definitions = {
            'STATUTORY_AUDIT': {
                'name': 'Statutory Audit',
                'category': 'Audit & Assurance',
                'description': 'Annual independent financial audit compliant with ICAN standards, NFRS/NAS, and Section 111 of Companies Act 2063.',
                'scope': 'Audit planning, internal controls review, sample testing of vouchers, verification of fixed assets, audit report formulation & AGM filing.',
                'icon': 'audit',
            },
            'TAX_VAT': {
                'name': 'Tax & VAT Compliance',
                'category': 'Direct & Indirect Tax',
                'description': 'Monthly e-VAT returns filing, annual income tax return (D1/D2/D3), and tax clearance certificates under Inland Revenue Department.',
                'scope': 'Monthly sales/purchase book reconciliations, input tax credit verification, withholding tax deduction returns, advance tax estimation.',
                'icon': 'tax',
            },
            'BOOKKEEPING': {
                'name': 'Accounting & Bookkeeping',
                'category': 'Accounting Services',
                'description': 'General ledger maintenance, monthly bank reconciliations, inventory books, and periodic management accounts.',
                'scope': 'Daily/weekly voucher recording, bank statement reconciliations, debtor/creditor ledger aging, monthly trial balance generation.',
                'icon': 'book',
            },
            'OCR_COMPLIANCE': {
                'name': 'Company Registrar (OCR) Filing',
                'category': 'Corporate Secretarial',
                'description': 'Annual filings with Office of Company Registrar including Form 21, auditor appointment notices, and share capital updates.',
                'scope': 'Filing annual returns within 6 months of FY end, registering board resolutions, updating directors register, share transfers.',
                'icon': 'ocr',
            },
            'INTERNAL_AUDIT': {
                'name': 'Internal Audit & Risk Controls',
                'category': 'Risk Advisory',
                'description': 'Evaluation of internal financial controls, standard operating procedure (SOP) reviews, and operational risk mitigation.',
                'scope': 'Quarterly operational audits, procurement fraud prevention, regulatory compliance spot checks, recommendations to audit committee.',
                'icon': 'internal',
            },
            'TDS_WITHHOLDING': {
                'name': 'TDS Advisory & Withholding Slips',
                'category': 'Tax Withholding',
                'description': 'Withholding tax calculation, payment verification, and bi-annual e-TDS reconciliation with IRD portal.',
                'scope': 'Determination of applicable TDS rates (1.5%, 10%, 15%), verifying deposit vouchers, generating client withholding certificates.',
                'icon': 'tds',
            },
            'ADVISORY': {
                'name': 'Financial Advisory & Due Diligence',
                'category': 'Special Advisory',
                'description': 'Mergers, company valuations, business restructuring, and capital raising advisory under Nepal regulatory frameworks.',
                'scope': 'Valuation of equity shares under discounted cash flow (DCF), financial due diligence for foreign direct investment (FDI), capital structuring.',
                'icon': 'advisory',
            },
        }

        subscribed_services = []
        for s_code in (client.services or []):
            s_info = service_definitions.get(s_code, {
                'name': SERVICE_DICT.get(s_code, s_code),
                'category': 'Practice Engagement',
                'description': 'Custom professional chartered accountancy service tailored to client requirements.',
                'scope': 'Scope tailored under engagement contract.',
                'icon': 'general',
            })
            # Count related tasks & compliance for this service
            subscribed_services.append({
                'code': s_code,
                'name': s_info['name'],
                'category': s_info['category'],
                'description': s_info['description'],
                'scope': s_info['scope'],
                'icon': s_info['icon'],
            })

        available_services = [
            {'code': k, 'name': v['name'], 'category': v['category'], 'description': v['description'], 'scope': v['scope']}
            for k, v in service_definitions.items()
            if k not in (client.services or [])
        ]

        # 3. Tasks
        all_tasks = client.tasks.select_related('assigned_to').order_by('due_date', '-priority')
        tasks_todo = all_tasks.filter(status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS, Task.Status.UNDER_REVIEW])
        tasks_completed = all_tasks.filter(status=Task.Status.COMPLETED)
        tasks_urgent = all_tasks.filter(priority=Task.Priority.URGENT).exclude(status=Task.Status.COMPLETED)

        # 4. Documents & Requests
        documents = client.documents.select_related('uploaded_by').order_by('-created_at')
        total_storage_bytes = sum(d.file_size_bytes for d in documents)
        document_requests = client.document_requests.select_related('requested_by').order_by('due_date')
        pending_requests_count = document_requests.filter(status__in=[DocumentRequest.Status.PENDING, DocumentRequest.Status.REMINDED]).count()

        # 5. Compliance Deadlines
        compliance_deadlines = client.compliance_deadlines.select_related('assigned_to', 'reviewer', 'compliance_type').order_by('-due_date_ad')
        compliance_list = []
        for cd in compliance_deadlines:
            days = (cd.due_date_ad - today).days
            compliance_list.append({
                'obj': cd,
                'days_left': days,
                'is_urgent': days <= 3 and cd.status not in ['COMPLETED', 'FILED', 'CANCELLED'],
                'is_overdue': cd.is_overdue,
            })
        client_compliance_requirements = client.compliance_requirements.select_related('compliance_type', 'assigned_staff', 'reviewer').filter(is_active=True)

        # 6. Invoices & Billing
        invoices = client.invoices.order_by('-issue_date')
        total_invoiced_npr = sum((inv.total_amount_npr for inv in invoices), Decimal('0.00'))
        total_paid_npr = sum((inv.paid_amount_npr for inv in invoices), Decimal('0.00'))
        total_outstanding_npr = total_invoiced_npr - total_paid_npr

        # 7. Conversations & Messages
        conversations = client.conversations.prefetch_related('participants', 'messages__sender').order_by('-updated_at')
        active_conversation = conversations.first() if conversations.exists() else None

        # 8. Activity Log
        activities = client.activities.select_related('performed_by').order_by('-created_at')

        # 9. Calendar Events
        calendar_events = client.calendar_events.select_related('created_by').order_by('start_time')
        upcoming_calendar_events = calendar_events.filter(start_time__gte=timezone.now())
        past_calendar_events = calendar_events.filter(start_time__lt=timezone.now()).order_by('-start_time')

        # Upcoming Deadlines for Overview Card
        overview_deadlines = []
        for c_item in compliance_list:
            if c_item['obj'].status not in ['COMPLETED', 'FILED']:
                overview_deadlines.append({
                    'title': c_item['obj'].title,
                    'category': c_item['obj'].get_governing_act_display(),
                    'date_ad': c_item['obj'].due_date_ad,
                    'date_bs': c_item['obj'].due_date_bs,
                    'days_left': c_item['days_left'],
                    'is_urgent': c_item['is_urgent'],
                    'is_overdue': c_item['is_overdue'],
                    'type': 'compliance',
                })
        for t in tasks_todo:
            if t.due_date:
                t_days = (t.due_date - today).days
                overview_deadlines.append({
                    'title': t.title,
                    'category': f"Task ({t.get_priority_display()})",
                    'date_ad': t.due_date,
                    'date_bs': '',
                    'days_left': t_days,
                    'is_urgent': t_days <= 3,
                    'is_overdue': t_days < 0,
                    'type': 'task',
                })
        overview_deadlines.sort(key=lambda x: x['date_ad'])

        # Pre-calculated Tab counts
        tab_counts = {
            'overview': None,
            'services': len(subscribed_services),
            'tasks': all_tasks.count(),
            'documents': documents.count() + document_requests.count(),
            'compliance': compliance_deadlines.count(),
            'calendar': calendar_events.count(),
            'billing': invoices.count(),
            'messages': conversations.count(),
            'activity': activities.count(),
        }

        context = {
            'client': client,
            'active_tab': active_tab,
            'tab_counts': tab_counts,
            'breadcrumbs': [
                {'title': 'Clients', 'url': '/clients/'},
                {'title': client.display_business_name, 'url': ''},
            ],
            # Team
            'team_by_role': team_by_role,
            # Services
            'subscribed_services': subscribed_services,
            'available_services': available_services,
            # Tasks
            'all_tasks': all_tasks,
            'tasks_todo': tasks_todo,
            'tasks_completed': tasks_completed,
            'tasks_urgent_count': tasks_urgent.count(),
            # Documents
            'documents': documents,
            'total_storage_bytes': total_storage_bytes,
            'total_storage_mb': round(total_storage_bytes / (1024 * 1024), 2),
            'document_requests': document_requests,
            'pending_requests_count': pending_requests_count,
            # Compliance
            'compliance_list': compliance_list,
            'compliance_deadlines': compliance_deadlines,
            'client_compliance_requirements': client_compliance_requirements,
            'available_compliance_types': ComplianceType.objects.filter(firm=request.firm, is_active=True),
            # Calendar
            'calendar_events': calendar_events,
            'upcoming_calendar_events': upcoming_calendar_events,
            'past_calendar_events': past_calendar_events,
            # Billing
            'invoices': invoices,
            'total_invoiced_npr': total_invoiced_npr,
            'total_paid_npr': total_paid_npr,
            'total_outstanding_npr': total_outstanding_npr,
            # Messages
            'conversations': conversations,
            'active_conversation': active_conversation,
            # Activities
            'activities': activities,
            # Overview
            'overview_deadlines': overview_deadlines[:6],
            # Forms for modals
            'client_edit_form': ClientForm(instance=client, firm=request.firm),
            'assign_staff_form': AssignStaffForm(
                initial={
                    'assigned_manager': client.assigned_manager_id,
                    'assigned_staff': client.assigned_staff.values_list('id', flat=True),
                },
                firm=request.firm,
            ),
            'create_task_form': CreateClientTaskForm(firm=request.firm),
            'request_doc_form': RequestDocumentForm(),
            'send_message_form': SendMessageForm(),
            'upload_doc_form': UploadDocumentForm(),
            'create_invoice_form': CreateInvoiceForm(),
            'create_calendar_event_form': CreateCalendarEventForm(),
        }
        return render(request, self.template_name, context)


class ClientUploadDocumentView(PermissionRequiredMixin, View):
    """
    Uploads a document directly to the client's repository.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'upload_document'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = UploadDocumentForm(request.POST, request.FILES)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Could not upload document. Please check the file and form fields.'))
            return redirect_after_action(request, client)

        doc = form.save(commit=False)
        doc.firm = request.firm
        doc.client = client
        doc.uploaded_by = request.user
        doc.file_size_bytes = doc.file.size if doc.file else 0
        doc.save()

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.DOC_UPLOADED,
            description=f"Uploaded document '{doc.title}' ({doc.get_category_display()}) for FY {doc.fiscal_year}.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='Document',
            object_id=str(doc.id),
            description=f"Uploaded document '{doc.title}' for client {client.display_business_name}.",
        )

        msg = _(f"Document '{doc.title}' has been uploaded successfully.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect(f"/clients/{client.id}/?tab=documents")


class ClientCreateInvoiceView(PermissionRequiredMixin, View):
    """
    Generates a billing invoice for the client with 13% Nepal VAT calculation.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'manage_billing'

    def post(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)
        form = CreateInvoiceForm(request.POST)

        if not form.is_valid():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _('Could not generate invoice. Please check the entered amounts.'))
            return redirect_after_action(request, client)

        invoice = form.save(commit=False)
        invoice.firm = request.firm
        invoice.client = client
        invoice.vat_percent = Decimal('13.00')
        invoice.vat_amount_npr = round(invoice.subtotal_npr * Decimal('0.13'), 2)
        invoice.total_amount_npr = invoice.subtotal_npr + invoice.vat_amount_npr
        invoice.paid_amount_npr = invoice.total_amount_npr if invoice.status == Invoice.Status.PAID else Decimal('0.00')
        invoice.save()

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.INVOICE_PAID if invoice.status == Invoice.Status.PAID else ClientActivity.ActivityType.STATUS_CHANGED,
            description=f"Generated invoice {invoice.invoice_number} for NPR {invoice.total_amount_npr:,.2f} (Status: {invoice.get_status_display()}).",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='Invoice',
            object_id=str(invoice.id),
            description=f"Created invoice {invoice.invoice_number} for {client.display_business_name}: NPR {invoice.total_amount_npr}.",
        )

        msg = _(f"Invoice {invoice.invoice_number} generated successfully.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect(f"/clients/{client.id}/?tab=billing")


class ClientTaskToggleView(PermissionRequiredMixin, View):
    """
    Quickly toggles task completion status from the client tasks tab.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'edit_task'

    def post(self, request, client_id, task_id):
        client = get_firm_client_or_404(request, client_id)
        task = get_object_or_404(Task.objects.filter(firm=request.firm, client=client), id=task_id)

        if task.status == Task.Status.COMPLETED:
            task.status = Task.Status.TODO
            task.completed_at = None
            msg = f"Task '{task.title}' marked as Incomplete."
            activity_desc = f"Re-opened task: '{task.title}'."
        else:
            task.status = Task.Status.COMPLETED
            task.completed_at = timezone.now()
            msg = f"Task '{task.title}' marked as Completed."
            activity_desc = f"Completed task: '{task.title}'."

        task.save(update_fields=['status', 'completed_at'])

        ClientActivity.objects.create(
            firm=request.firm,
            client=client,
            activity_type=ClientActivity.ActivityType.TASK_COMPLETED,
            description=activity_desc,
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Task',
            object_id=str(task.id),
            description=f"{activity_desc} Client: {client.display_business_name}.",
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'status': task.status, 'message': msg})

        messages.success(request, _(msg))
        return redirect(f"/clients/{client.id}/?tab=tasks")


class ClientExportSingleView(PermissionRequiredMixin, View):
    """
    Exports a single client's profile summary to CSV with full audit trail.
    Strictly verifies User -> Firm -> Client.
    """
    firm_permission = 'view_client'

    def get(self, request, client_id):
        client = get_firm_client_or_404(request, client_id)

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f"CAFlow_Client_{client.pan_number or client.id}_{timezone.localdate()}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['CAFlow Nepal Practice Management - Client Dossier'])
        writer.writerow([])
        writer.writerow(['Client Name', client.name])
        writer.writerow(['Business / Legal Entity Name', client.display_business_name])
        writer.writerow(['IRD PAN Number', client.pan_number or 'N/A'])
        writer.writerow(['OCR Registration Number', client.registration_number or 'N/A'])
        writer.writerow(['Business Category', client.get_client_type_display()])
        writer.writerow(['Active Fiscal Year', client.fiscal_year])
        writer.writerow(['Official Email', client.email or 'N/A'])
        writer.writerow(['Contact Phone', client.phone or 'N/A'])
        writer.writerow(['Registered Address', f"{client.address}, {client.city}"])
        writer.writerow(['Client Status', client.get_status_display()])
        writer.writerow(['Lead CA / Manager', client.assigned_manager.get_full_name() if client.assigned_manager else 'Unassigned'])
        writer.writerow(['Active Services', ", ".join(client.services_display)])
        writer.writerow(['Profile Created Date', client.created_at.strftime('%Y-%m-%d %H:%M')])

        log_audit(
            request=request,
            action=AuditLog.ActionType.EXPORT,
            object_type='Client',
            object_id=str(client.id),
            description=f"Exported client dossier CSV for {client.display_business_name}.",
        )

        return response

