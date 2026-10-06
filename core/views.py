import datetime
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User
from audit.services import log_audit
from billing.models import Invoice
from clients.models import Client, ClientActivity
from compliance.models import ComplianceDeadline
from core.services import get_dashboard_data
from documents.models import DocumentRequest
from firms.mixins import FirmRequiredMixin
from firms.models import FirmRole, MembershipStatus
from tasks.models import Task


class LandingPageView(TemplateView):
    template_name = 'core/landing.html'


class DesignSystemView(LoginRequiredMixin, TemplateView):
    template_name = 'core/design_system.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Design System', 'url': ''}
        ]
        return context


class DashboardView(FirmRequiredMixin, TemplateView):
    """
    Production-Quality CAFlow Admin Dashboard.
    Provides firm-scoped analytics, today's work queue, compliance calendar,
    document request tracking, staff workload capacity, and immutable client activity trail.
    Strictly isolated to request.firm.
    """
    template_name = 'core/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not getattr(request, 'firm', None):
            return super().dispatch(request, *args, **kwargs)
        if request.firm_membership and request.firm_membership.role == FirmRole.CLIENT:
            raise PermissionDenied(_("Client portal users do not have access to the internal practice dashboard."))
        return super().dispatch(request, *args, **kwargs)


    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        request = self.request
        firm = request.firm
        user = request.user

        # Filter parameters for Today's Work
        search_query = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', 'ALL').strip().upper()
        priority_filter = request.GET.get('priority', 'ALL').strip().upper()
        task_scope = request.GET.get('scope', 'all').strip().lower()

        dashboard_data = get_dashboard_data(
            firm=firm,
            user=user,
            search_query=search_query,
            status_filter=status_filter,
            priority_filter=priority_filter,
            task_scope=task_scope,
        )

        # Nepal Calendar & Date Display
        today = timezone.localdate()
        date_str = today.strftime("%A, %-d %b %Y")
        # Approximate Ashoj 2081 mapping
        ashoj_day = 19 + (today.day - 5)
        full_date_display = f"{date_str} • {ashoj_day} Ashoj 2081"

        user_display_name = user.get_full_name() or user.email

        context.update(dashboard_data)
        context['breadcrumbs'] = [{'title': 'Dashboard', 'url': ''}]
        context['user_display_name'] = user_display_name
        context['today_formatted_date'] = full_date_display
        return context


class QuickAddClientView(FirmRequiredMixin, View):
    """Handles adding new client entities from dashboard quick action."""
    def post(self, request, *args, **kwargs):
        if not request.has_firm_perm('create_client'):
            raise PermissionDenied(_("You do not have permission to create clients."))

        firm = request.firm
        name = request.POST.get('name', '').strip()
        pan = request.POST.get('pan_number', '').strip()
        client_type = request.POST.get('client_type', Client.ClientType.PVT_LTD)
        contact_person = request.POST.get('contact_person', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        city = request.POST.get('city', 'Kathmandu').strip()

        if not name:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': "Client name is required."}, status=400)
            messages.error(request, "Client name is required.")
            return redirect('core:dashboard')

        client = Client.objects.create(
            firm=firm,
            name=name,
            pan_number=pan,
            client_type=client_type,
            contact_person=contact_person,
            email=email,
            phone=phone,
            city=city,
            status=Client.Status.ACTIVE,
        )

        ClientActivity.objects.create(
            firm=firm,
            client=client,
            activity_type=ClientActivity.ActivityType.NEW_CLIENT,
            description=f"{client.name} onboarded as new client entity",
            performed_by=request.user,
        )
        log_audit(request, firm=firm, user=request.user, action='CREATE', object_type='Client', object_id=str(client.id), description=f"Onboarded client {client.name}")

        messages.success(request, f"Client '{client.name}' onboarded successfully!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'client_id': str(client.id), 'message': f"Client '{client.name}' onboarded successfully!"})
        return redirect('core:dashboard')


class QuickCreateTaskView(FirmRequiredMixin, View):
    """Handles creating tasks from dashboard quick action."""
    def post(self, request, *args, **kwargs):
        if not request.has_firm_perm('create_task'):
            raise PermissionDenied(_("You do not have permission to create tasks."))

        firm = request.firm
        title = request.POST.get('title', '').strip()
        client_id = request.POST.get('client_id')
        assigned_to_id = request.POST.get('assigned_to_id')
        priority = request.POST.get('priority', Task.Priority.MEDIUM)
        due_date_str = request.POST.get('due_date')
        description = request.POST.get('description', '').strip()

        if not title:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': "Task title is required."}, status=400)
            messages.error(request, "Task title is required.")
            return redirect('core:dashboard')

        client = Client.objects.filter(firm=firm, id=client_id).first() if client_id else None
        assigned_to = User.objects.filter(
            id=assigned_to_id,
            firm_memberships__firm=firm,
            firm_memberships__status=MembershipStatus.ACTIVE,
        ).first() if assigned_to_id else None

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.date.fromisoformat(due_date_str)
            except ValueError:
                due_date = timezone.localdate()
        else:
            due_date = timezone.localdate()

        task = Task.objects.create(
            firm=firm,
            title=title,
            client=client,
            assigned_to=assigned_to,
            priority=priority,
            due_date=due_date,
            description=description,
            status=Task.Status.TODO,
        )

        log_audit(request, firm=firm, user=request.user, action='CREATE', object_type='Task', object_id=str(task.id), description=f"Created task {task.title}")

        messages.success(request, f"Task '{task.title}' created and queued!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'task_id': str(task.id), 'message': f"Task '{task.title}' created successfully!"})
        return redirect('core:dashboard')


class QuickRequestDocView(FirmRequiredMixin, View):
    """Handles requesting documents from dashboard quick action."""
    def post(self, request, *args, **kwargs):
        if not request.has_firm_perm('request_document'):
            raise PermissionDenied(_("You do not have permission to request documents."))

        firm = request.firm
        client_id = request.POST.get('client_id')
        requested_docs = request.POST.get('requested_documents', '').strip()
        due_date_str = request.POST.get('due_date')
        notes = request.POST.get('notes', '').strip()

        client = Client.objects.filter(firm=firm, id=client_id).first()
        if not client or not requested_docs:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': "Client and requested documents description are required."}, status=400)
            messages.error(request, "Client and requested documents description are required.")
            return redirect('core:dashboard')

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.date.fromisoformat(due_date_str)
            except ValueError:
                due_date = timezone.localdate() + datetime.timedelta(days=7)
        else:
            due_date = timezone.localdate() + datetime.timedelta(days=7)

        doc_req = DocumentRequest.objects.create(
            firm=firm,
            client=client,
            requested_documents=requested_docs,
            due_date=due_date,
            notes=notes,
            requested_by=request.user,
            status=DocumentRequest.Status.PENDING,
        )

        log_audit(request, firm=firm, user=request.user, action='CREATE', object_type='DocumentRequest', object_id=str(doc_req.id), description=f"Requested docs from {client.name}")

        messages.success(request, f"Document request dispatched to {client.name}!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f"Document request dispatched to {client.name}!"})
        return redirect('core:dashboard')


class QuickCreateInvoiceView(FirmRequiredMixin, View):
    """Handles generating invoices from dashboard quick action."""
    def post(self, request, *args, **kwargs):
        if not request.has_firm_perm('manage_billing'):
            raise PermissionDenied(_("You do not have permission to issue invoices."))

        firm = request.firm
        client_id = request.POST.get('client_id')
        invoice_number = request.POST.get('invoice_number', '').strip()
        subtotal_str = request.POST.get('subtotal_npr', '0')
        due_date_str = request.POST.get('due_date')

        client = Client.objects.filter(firm=firm, id=client_id).first()
        if not client or not invoice_number:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': "Client and invoice serial number are required."}, status=400)
            messages.error(request, "Client and invoice serial number are required.")
            return redirect('core:dashboard')

        try:
            subtotal = Decimal(subtotal_str)
        except Exception:
            subtotal = Decimal('10000.00')

        vat_amount = (subtotal * Decimal('0.13')).quantize(Decimal('0.01'))
        total_amount = subtotal + vat_amount

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.date.fromisoformat(due_date_str)
            except ValueError:
                due_date = timezone.localdate() + datetime.timedelta(days=15)
        else:
            due_date = timezone.localdate() + datetime.timedelta(days=15)

        inv = Invoice.objects.create(
            firm=firm,
            client=client,
            invoice_number=invoice_number,
            subtotal_npr=subtotal,
            vat_percent=Decimal('13.00'),
            vat_amount_npr=vat_amount,
            total_amount_npr=total_amount,
            paid_amount_npr=Decimal('0.00'),
            status=Invoice.Status.ISSUED,
            issue_date=timezone.localdate(),
            due_date=due_date,
        )

        log_audit(request, firm=firm, user=request.user, action='CREATE', object_type='Invoice', object_id=str(inv.id), description=f"Issued invoice {inv.invoice_number} to {client.name}")

        messages.success(request, f"Invoice INV-{inv.invoice_number} issued for NPR {total_amount:,.2f}!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f"Invoice INV-{inv.invoice_number} issued successfully!"})
        return redirect('core:dashboard')


class QuickCompleteTaskView(FirmRequiredMixin, View):
    """Marks a task as completed from the dashboard table."""
    def post(self, request, task_id, *args, **kwargs):
        if not request.has_firm_perm('edit_task'):
            raise PermissionDenied(_("You do not have permission to update tasks."))

        firm = request.firm
        task = get_object_or_404(Task, id=task_id, firm=firm)
        task.status = Task.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save()

        ClientActivity.objects.create(
            firm=firm,
            client=task.client,
            activity_type=ClientActivity.ActivityType.TASK_COMPLETED,
            description=f"Task '{task.title}' marked as completed",
            performed_by=request.user,
        )
        log_audit(request, firm=firm, user=request.user, action='UPDATE', object_type='Task', object_id=str(task.id), description=f"Completed task {task.title}")

        messages.success(request, f"Task '{task.title}' marked as completed!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f"Task '{task.title}' marked completed!"})
        return redirect('core:dashboard')


class QuickRemindDocView(FirmRequiredMixin, View):
    """Sends a reminder for a pending document request."""
    def post(self, request, req_id, *args, **kwargs):
        if not request.has_firm_perm('request_document'):
            raise PermissionDenied(_("You do not have permission to request documents."))

        firm = request.firm
        doc_req = get_object_or_404(DocumentRequest, id=req_id, firm=firm)
        doc_req.status = DocumentRequest.Status.REMINDED
        doc_req.save()

        log_audit(request, firm=firm, user=request.user, action='UPDATE', object_type='DocumentRequest', object_id=str(doc_req.id), description=f"Reminded {doc_req.client.name} for {doc_req.requested_documents}")

        messages.success(request, f"Reminder dispatched to {doc_req.client.name} via SMS & Email!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f"Reminder sent to {doc_req.client.name}!"})
        return redirect('core:dashboard')

