import datetime
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView

from audit.services import log_audit
from clients.models import Client
from documents.models import Document
from firms.mixins import FirmRequiredMixin, PermissionRequiredMixin
from firms.models import FirmMembership, MembershipStatus
from tasks.models import Task
from compliance.forms import (
    ComplianceDeadlineForm,
    ComplianceTypeForm,
    ClientComplianceRequirementForm,
    ComplianceStatusTransitionForm,
    LinkTaskForm,
    LinkDocumentForm,
)
from compliance.models import (
    ComplianceDeadline,
    ComplianceType,
    ClientComplianceRequirement,
    ComplianceActivity,
)
from compliance.services import (
    ensure_default_compliance_types,
    get_compliance_dashboard_metrics,
    check_and_update_overdue_deadlines,
    transition_compliance_status,
    create_next_recurring_deadline,
    generate_deadlines_from_client_requirements,
)


class ComplianceDeadlineListView(PermissionRequiredMixin, ListView):
    """
    Central Compliance Hub for CA Practice.
    Shows dashboard metrics (due today, due this week, overdue, waiting for client, awaiting review, completed),
    supports filtering by status, timeframe, type, client, and assigned staff.
    """
    firm_permission = 'view_compliance'
    model = ComplianceDeadline
    template_name = 'compliance/compliance_list.html'
    context_object_name = 'deadlines'
    paginate_by = 15

    def get_queryset(self):
        firm = self.request.firm
        # Ensure system default types exist
        ensure_default_compliance_types(firm)
        # Auto-identify overdue items
        check_and_update_overdue_deadlines(firm)

        qs = ComplianceDeadline.objects.filter(firm=firm).select_related(
            'client', 'compliance_type', 'assigned_to', 'reviewer'
        ).prefetch_related('tasks', 'documents')

        today = timezone.localdate()
        week_end = today + datetime.timedelta(days=7)

        # 1. Search Query
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(period__icontains=q) |
                Q(due_date_bs__icontains=q) |
                Q(notes__icontains=q) |
                Q(filing_reference_number__icontains=q) |
                Q(client__name__icontains=q) |
                Q(client__business_name__icontains=q) |
                Q(client__pan_number__icontains=q) |
                Q(assigned_to__first_name__icontains=q) |
                Q(assigned_to__last_name__icontains=q)
            )

        # 2. Scope / Quick Metric Filter
        scope = self.request.GET.get('scope', '').strip().lower()
        if scope == 'due_today':
            qs = qs.filter(due_date_ad=today).exclude(status__in=[
                ComplianceDeadline.Status.COMPLETED,
                ComplianceDeadline.Status.FILED,
                ComplianceDeadline.Status.CANCELLED,
            ])
        elif scope == 'due_this_week':
            qs = qs.filter(due_date_ad__gte=today, due_date_ad__lte=week_end).exclude(status__in=[
                ComplianceDeadline.Status.COMPLETED,
                ComplianceDeadline.Status.FILED,
                ComplianceDeadline.Status.CANCELLED,
            ])
        elif scope == 'overdue':
            qs = qs.filter(
                Q(status=ComplianceDeadline.Status.OVERDUE) |
                (Q(due_date_ad__lt=today) & ~Q(status__in=[
                    ComplianceDeadline.Status.COMPLETED,
                    ComplianceDeadline.Status.FILED,
                    ComplianceDeadline.Status.CANCELLED,
                ]))
            )
        elif scope == 'waiting_for_client':
            qs = qs.filter(status=ComplianceDeadline.Status.WAITING_FOR_CLIENT)
        elif scope == 'awaiting_review':
            qs = qs.filter(status=ComplianceDeadline.Status.READY_FOR_REVIEW)
        elif scope == 'completed':
            qs = qs.filter(status__in=[ComplianceDeadline.Status.COMPLETED, ComplianceDeadline.Status.FILED])

        # 3. Explicit Status Filter
        status_filter = self.request.GET.get('status', '').strip().upper()
        if status_filter and status_filter != 'ALL':
            qs = qs.filter(status=status_filter)

        # 4. Compliance Type Filter
        type_id = self.request.GET.get('compliance_type', '').strip()
        if type_id:
            qs = qs.filter(compliance_type_id=type_id)

        # 5. Governing Act Filter
        act_filter = self.request.GET.get('act', '').strip().upper()
        if act_filter and act_filter != 'ALL':
            qs = qs.filter(governing_act=act_filter)

        # 6. Client Filter
        client_id = self.request.GET.get('client', '').strip()
        if client_id:
            qs = qs.filter(client_id=client_id)

        # 7. Assigned Staff Filter
        assigned_id = self.request.GET.get('assigned_to', '').strip()
        if assigned_id:
            qs = qs.filter(assigned_to_id=assigned_id)

        return qs.order_by('due_date_ad', '-priority')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm
        today = timezone.localdate()

        context['breadcrumbs'] = [
            {'title': 'Compliance', 'url': ''},
        ]
        context['dashboard_metrics'] = get_compliance_dashboard_metrics(firm)
        context['today_ad'] = today
        context['today_str'] = today.strftime('%Y-%m-%d')

        # Form and filter options
        context['create_form'] = ComplianceDeadlineForm(firm=firm)
        context['compliance_types'] = ComplianceType.objects.filter(firm=firm, is_active=True).order_by('name')
        context['clients_list'] = Client.objects.filter(firm=firm, is_active=True).order_by('business_name', 'name')

        active_members = FirmMembership.objects.filter(
            firm=firm, status=MembershipStatus.ACTIVE, is_active=True
        ).select_related('user')
        context['team_members'] = [m.user for m in active_members]

        # Selected filters for UI retention
        context['selected_scope'] = self.request.GET.get('scope', 'all')
        context['selected_status'] = self.request.GET.get('status', 'ALL')
        context['selected_type'] = self.request.GET.get('compliance_type', '')
        context['selected_act'] = self.request.GET.get('act', 'ALL')
        context['selected_client'] = self.request.GET.get('client', '')
        context['selected_assigned'] = self.request.GET.get('assigned_to', '')
        context['search_query'] = self.request.GET.get('q', '')

        # Act Choices
        context['act_choices'] = ComplianceDeadline.GoverningAct.choices
        context['status_choices'] = ComplianceDeadline.Status.choices

        return context


class ComplianceDeadlineCreateView(PermissionRequiredMixin, View):
    """
    Creates a new statutory filing deadline.
    Supports regular form submission and AJAX modal submit.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, *args, **kwargs):
        firm = request.firm
        form = ComplianceDeadlineForm(request.POST, firm=firm)

        if form.is_valid():
            deadline = form.save(commit=False)
            deadline.firm = firm

            # Derive governing act from type if not explicitly set
            if deadline.compliance_type and not deadline.governing_act:
                deadline.governing_act = deadline.compliance_type.category

            deadline.save()
            form.save_m2m()

            # Record activity & audit
            ComplianceActivity.objects.create(
                firm=firm,
                deadline=deadline,
                action='CREATED',
                to_status=deadline.status,
                description=f"Compliance deadline '{deadline.title}' scheduled for {deadline.due_date_ad} (BS {deadline.due_date_bs}).",
                performed_by=request.user,
            )
            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='CREATE',
                object_type='ComplianceDeadline',
                object_id=str(deadline.id),
                description=f"Created compliance deadline {deadline.title} for {deadline.client.name if deadline.client else 'General'}",
            )

            # In-app notification to staff
            if deadline.assigned_to and deadline.assigned_to != request.user:
                from notifications.models import Notification
                from notifications.services import create_notification
                create_notification(
                    recipient=deadline.assigned_to,
                    firm=firm,
                    title=f"Compliance Assigned: {deadline.title}",
                    message=f"You have been assigned to prepare compliance filing for {deadline.client.name if deadline.client else 'General'} due on BS {deadline.due_date_bs}.",
                    notification_type=Notification.NotificationType.COMPLIANCE,
                    action_url=f"/compliance/?id={deadline.id}",
                )

            messages.success(request, f"Compliance filing '{deadline.title}' scheduled successfully!")

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                return JsonResponse({
                    'success': True,
                    'deadline_id': str(deadline.id),
                    'message': f"Filing '{deadline.title}' created successfully!",
                })

            next_url = request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('compliance:compliance_list')
        else:
            errors_str = " ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                return JsonResponse({'success': False, 'message': errors_str, 'errors': form.errors}, status=400)
            messages.error(request, f"Could not create compliance deadline: {errors_str}")
            return redirect('compliance:compliance_list')


class ComplianceDeadlineDetailView(PermissionRequiredMixin, View):
    """
    Renders compliance item details or returns JSON for detail modal.
    """
    firm_permission = 'view_compliance'

    def get(self, request, deadline_id, *args, **kwargs):
        firm = request.firm
        deadline = get_object_or_404(
            ComplianceDeadline.objects.filter(firm=firm).select_related(
                'client', 'compliance_type', 'assigned_to', 'reviewer'
            ).prefetch_related('tasks', 'documents', 'activities__performed_by'),
            id=deadline_id
        )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            tasks_data = [{'id': str(t.id), 'title': t.title, 'status': t.get_status_display()} for t in deadline.tasks.all()]
            docs_data = [{'id': str(d.id), 'title': d.title, 'category': d.get_category_display(), 'url': d.file.url if d.file else ''} for d in deadline.documents.all()]
            activities_data = [
                {
                    'action': a.action,
                    'description': a.description,
                    'user': a.performed_by.get_full_name() if a.performed_by else 'System',
                    'date': a.created_at.strftime('%Y-%m-%d %H:%M'),
                } for a in deadline.activities.all()[:10]
            ]
            return JsonResponse({
                'id': str(deadline.id),
                'title': deadline.title,
                'client_name': deadline.client.name if deadline.client else 'General Practice',
                'client_id': str(deadline.client.id) if deadline.client else None,
                'period': deadline.period,
                'due_date_bs': deadline.due_date_bs,
                'due_date_ad': deadline.due_date_ad.strftime('%Y-%m-%d'),
                'status': deadline.status,
                'status_display': deadline.get_status_display(),
                'priority': deadline.priority,
                'priority_display': deadline.get_priority_display(),
                'assigned_to': deadline.assigned_to.get_full_name() if deadline.assigned_to else 'Unassigned',
                'assigned_to_id': str(deadline.assigned_to.id) if deadline.assigned_to else None,
                'reviewer': deadline.reviewer.get_full_name() if deadline.reviewer else 'None',
                'reviewer_id': str(deadline.reviewer.id) if deadline.reviewer else None,
                'governing_act': deadline.get_governing_act_display(),
                'description': deadline.description,
                'notes': deadline.notes,
                'filing_reference_number': deadline.filing_reference_number,
                'completion_date': deadline.completion_date.strftime('%Y-%m-%d') if deadline.completion_date else '',
                'is_overdue': deadline.is_overdue,
                'days_remaining': deadline.days_remaining,
                'stage_index': deadline.workflow_stage_index,
                'tasks': tasks_data,
                'documents': docs_data,
                'activities': activities_data,
            })

        context = {
            'deadline': deadline,
            'status_form': ComplianceStatusTransitionForm(initial={'status': deadline.status}),
            'link_task_form': LinkTaskForm(firm=firm, client=deadline.client),
            'link_doc_form': LinkDocumentForm(firm=firm, client=deadline.client),
            'breadcrumbs': [
                {'title': 'Compliance', 'url': reverse('compliance:compliance_list')},
                {'title': deadline.title, 'url': ''},
            ],
        }
        return render(request, 'compliance/compliance_detail.html', context)


class ComplianceStatusUpdateView(PermissionRequiredMixin, View):
    """
    Transitions the workflow status of a compliance deadline:
    Upcoming -> In Progress -> Waiting for Client -> Ready for Review -> Filed -> Completed.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, deadline_id, *args, **kwargs):
        firm = request.firm
        deadline = get_object_or_404(ComplianceDeadline.objects.filter(firm=firm), id=deadline_id)

        new_status = request.POST.get('status', '').strip().upper()
        notes = request.POST.get('notes', '').strip()
        filing_ref = request.POST.get('filing_reference_number', '').strip()
        completion_date_str = request.POST.get('completion_date')

        completion_date = None
        if completion_date_str:
            try:
                completion_date = datetime.date.fromisoformat(completion_date_str)
            except ValueError:
                completion_date = timezone.localdate()

        valid_statuses = [choice[0] for choice in ComplianceDeadline.Status.choices]
        if new_status not in valid_statuses:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': f"Invalid status: {new_status}"}, status=400)
            messages.error(request, f"Invalid status {new_status}")
            return redirect('compliance:compliance_list')

        transition_compliance_status(
            deadline=deadline,
            new_status=new_status,
            user=request.user,
            request=request,
            notes=notes,
            filing_reference_number=filing_ref,
            completion_date=completion_date,
        )

        messages.success(request, f"Status for '{deadline.title}' updated to {deadline.get_status_display()}!")

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'status': deadline.status,
                'status_display': deadline.get_status_display(),
                'stage_index': deadline.workflow_stage_index,
                'message': f"Status updated to {deadline.get_status_display()}!",
            })

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('compliance:compliance_list')


class ComplianceDeadlineUpdateView(PermissionRequiredMixin, View):
    """
    Edits compliance deadline details.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, deadline_id, *args, **kwargs):
        firm = request.firm
        deadline = get_object_or_404(ComplianceDeadline.objects.filter(firm=firm), id=deadline_id)
        form = ComplianceDeadlineForm(request.POST, instance=deadline, firm=firm)

        if form.is_valid():
            updated_deadline = form.save()
            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='UPDATE',
                object_type='ComplianceDeadline',
                object_id=str(updated_deadline.id),
                description=f"Updated compliance deadline {updated_deadline.title}",
            )
            ComplianceActivity.objects.create(
                firm=firm,
                deadline=updated_deadline,
                action='EDITED',
                to_status=updated_deadline.status,
                description="Deadline attributes updated.",
                performed_by=request.user,
            )
            messages.success(request, f"Compliance filing '{updated_deadline.title}' updated successfully!")

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Updated successfully!'})

            next_url = request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('compliance:compliance_list')
        else:
            errors_str = " ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': errors_str, 'errors': form.errors}, status=400)
            messages.error(request, f"Could not update deadline: {errors_str}")
            return redirect('compliance:compliance_list')


class ComplianceDeadlineDeleteView(PermissionRequiredMixin, View):
    """
    Deletes a compliance deadline item.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, deadline_id, *args, **kwargs):
        firm = request.firm
        deadline = get_object_or_404(ComplianceDeadline.objects.filter(firm=firm), id=deadline_id)
        title = deadline.title

        log_audit(
            request=request,
            firm=firm,
            user=request.user,
            action='DELETE',
            object_type='ComplianceDeadline',
            object_id=str(deadline.id),
            description=f"Deleted compliance deadline '{title}'",
        )
        deadline.delete()

        messages.success(request, f"Compliance filing '{title}' removed.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f"Filing '{title}' removed."})
        return redirect('compliance:compliance_list')


class ComplianceLinkTaskView(PermissionRequiredMixin, View):
    """
    Connects an existing task or creates a new task connected to this compliance deadline.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, deadline_id, *args, **kwargs):
        firm = request.firm
        deadline = get_object_or_404(ComplianceDeadline.objects.filter(firm=firm), id=deadline_id)

        task_id = request.POST.get('existing_task_id')
        new_title = request.POST.get('new_task_title', '').strip()

        if task_id:
            task = get_object_or_404(Task.objects.filter(firm=firm), id=task_id)
            deadline.tasks.add(task)
            msg = f"Task '{task.title}' linked to compliance deadline!"
        elif new_title:
            task = Task.objects.create(
                firm=firm,
                title=new_title,
                client=deadline.client,
                assigned_to=deadline.assigned_to,
                priority=deadline.priority,
                due_date=deadline.due_date_ad,
                description=f"Task spawned for statutory filing: {deadline.title}\n{deadline.description}",
                status=Task.Status.TODO,
                service=deadline.compliance_type.code if deadline.compliance_type else 'TAX_VAT',
            )
            deadline.tasks.add(task)
            msg = f"New task '{task.title}' created and linked!"
        else:
            msg = "No task selected or created."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=400)
            messages.warning(request, msg)
            return redirect('compliance:compliance_list')

        ComplianceActivity.objects.create(
            firm=firm,
            deadline=deadline,
            action='TASK_LINKED',
            description=msg,
            performed_by=request.user,
        )

        messages.success(request, msg)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})
        return redirect('compliance:compliance_list')


class ComplianceLinkDocumentView(PermissionRequiredMixin, View):
    """
    Connects an existing client document or uploads a new document for this compliance filing.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, deadline_id, *args, **kwargs):
        firm = request.firm
        deadline = get_object_or_404(ComplianceDeadline.objects.filter(firm=firm), id=deadline_id)

        doc_id = request.POST.get('existing_document_id')
        uploaded_file = request.FILES.get('upload_file')
        doc_title = request.POST.get('document_title', '').strip()

        if doc_id:
            doc = get_object_or_404(Document.objects.filter(firm=firm), id=doc_id)
            deadline.documents.add(doc)
            msg = f"Document '{doc.title}' linked to compliance filing!"
        elif uploaded_file:
            if not deadline.client:
                msg = "Cannot upload file to general firm deadline without a designated client."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': msg}, status=400)
                messages.error(request, msg)
                return redirect('compliance:compliance_list')

            title = doc_title or uploaded_file.name
            doc = Document.objects.create(
                firm=firm,
                client=deadline.client,
                title=title,
                file=uploaded_file,
                category=Document.Category.TAX_FILING,
                uploaded_by=request.user,
                description=f"Attached to compliance filing: {deadline.title}",
            )
            deadline.documents.add(doc)
            msg = f"Document '{doc.title}' uploaded and attached!"
        else:
            msg = "No document selected or uploaded."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': msg}, status=400)
            messages.warning(request, msg)
            return redirect('compliance:compliance_list')

        ComplianceActivity.objects.create(
            firm=firm,
            deadline=deadline,
            action='DOC_LINKED',
            description=msg,
            performed_by=request.user,
        )

        messages.success(request, msg)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})
        return redirect('compliance:compliance_list')


class ComplianceTypeManageView(PermissionRequiredMixin, ListView):
    """
    Allows CA firms to inspect, create, and customize statutory compliance types.
    """
    firm_permission = 'manage_compliance'
    model = ComplianceType
    template_name = 'compliance/compliance_types.html'
    context_object_name = 'types'

    def get_queryset(self):
        firm = self.request.firm
        ensure_default_compliance_types(firm)
        return ComplianceType.objects.filter(firm=firm).order_by('category', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Compliance', 'url': reverse('compliance:compliance_list')},
            {'title': 'Configurable Compliance Types', 'url': ''},
        ]
        context['form'] = ComplianceTypeForm()
        return context

    def post(self, request, *args, **kwargs):
        firm = request.firm
        form = ComplianceTypeForm(request.POST)
        if form.is_valid():
            comp_type = form.save(commit=False)
            comp_type.firm = firm
            comp_type.save()

            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='CREATE',
                object_type='ComplianceType',
                object_id=str(comp_type.id),
                description=f"Configured compliance type '{comp_type.name}'",
            )
            messages.success(request, f"Compliance type '{comp_type.name}' saved!")
            return redirect('compliance:compliance_types')
        else:
            messages.error(request, "Failed to save compliance type. Check input fields.")
            return self.get(request, *args, **kwargs)


class ClientRequirementManageView(PermissionRequiredMixin, View):
    """
    Configures which clients require which compliance filings.
    Fulfills requirement: 'Do not assume every client has every compliance requirement.'
    """
    firm_permission = 'manage_compliance'

    def post(self, request, *args, **kwargs):
        firm = request.firm
        form = ClientComplianceRequirementForm(request.POST, firm=firm)

        if form.is_valid():
            req = form.save(commit=False)
            req.firm = firm
            req.save()

            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='CREATE',
                object_type='ClientComplianceRequirement',
                object_id=str(req.id),
                description=f"Subscribed {req.client.name} to {req.compliance_type.name}",
            )
            messages.success(request, f"Subscribed {req.client.name} to '{req.compliance_type.name}' schedule!")

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Requirement configured!'})

            next_url = request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('compliance:compliance_list')
        else:
            errors_str = " ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': errors_str}, status=400)
            messages.error(request, f"Could not save client requirement: {errors_str}")
            return redirect('compliance:compliance_list')


class GenerateClientDeadlinesView(PermissionRequiredMixin, View):
    """
    Generates compliance deadlines from active client requirements for a targeted return period.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, *args, **kwargs):
        firm = request.firm
        period_name = request.POST.get('period_name', '').strip()
        due_bs = request.POST.get('due_date_bs', '').strip()
        due_ad_str = request.POST.get('due_date_ad', '').strip()

        if not due_ad_str:
            messages.error(request, "Due Date (AD) is required to generate deadlines.")
            return redirect('compliance:compliance_list')

        try:
            due_ad = datetime.date.fromisoformat(due_ad_str)
        except ValueError:
            messages.error(request, "Invalid Gregorian date.")
            return redirect('compliance:compliance_list')

        created = generate_deadlines_from_client_requirements(
            firm=firm,
            target_period_name=period_name,
            due_date_bs=due_bs,
            due_date_ad=due_ad,
            user=request.user,
        )

        count = len(created)
        log_audit(
            request=request,
            firm=firm,
            user=request.user,
            action='BULK_GENERATE',
            object_type='ComplianceDeadline',
            description=f"Generated {count} deadlines for period '{period_name}'",
        )

        messages.success(request, f"Generated {count} compliance filing deadlines for subscribed clients!")
        return redirect('compliance:compliance_list')


class CheckOverdueDeadlinesView(PermissionRequiredMixin, View):
    """
    Explicitly triggers auto-identification of overdue compliance deadlines.
    """
    firm_permission = 'manage_compliance'

    def post(self, request, *args, **kwargs):
        firm = request.firm
        count = check_and_update_overdue_deadlines(firm=firm)
        messages.info(request, f"Scan complete: {count} deadlines identified as Overdue.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'count': count, 'message': f"{count} items updated to Overdue."})
        return redirect('compliance:compliance_list')
