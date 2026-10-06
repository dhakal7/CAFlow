import json
import datetime
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User
from audit.services import log_audit
from clients.constants import SERVICE_CHOICES, SERVICE_DICT
from clients.models import Client, ClientActivity
from firms.mixins import FirmRequiredMixin, PermissionRequiredMixin
from firms.models import FirmMembership, MembershipStatus
from tasks.forms import (
    TaskAttachmentForm,
    TaskChecklistItemForm,
    TaskCommentForm,
    TaskForm,
    WorkflowTemplateForm,
)
from tasks.models import (
    Task,
    TaskActivity,
    TaskAttachment,
    TaskChecklistItem,
    TaskComment,
    WorkflowTemplate,
    WorkflowTemplateItem,
)
from notifications.models import Notification
from notifications.services import create_notification
from tasks.services import (
    apply_template_to_task,
    create_next_recurring_task,
    ensure_firm_workflow_templates,
    record_task_activity,
)


def get_firm_task_or_404(request, task_id):
    """
    Enforces strict tenant isolation for tasks:
    User -> Firm -> Task.
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
    
    return get_object_or_404(
        Task.objects.filter(firm=firm).select_related('client', 'assigned_to', 'created_by'),
        id=task_id,
    )


class TaskListView(PermissionRequiredMixin, TemplateView):
    """
    Primary Task & Workflow Management view supporting:
    - Board View (Pending, In Progress, Review, Completed)
    - List View (Table with sorting, pagination, quick actions)
    - Calendar View (Deadline calendar by due date)
    - Search & multi-parameter filtering
    """
    firm_permission = 'view_task'
    template_name = 'tasks/task_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm
        user = self.request.user

        # Ensure default workflow templates exist
        ensure_firm_workflow_templates(firm, user=user)

        # Base QuerySet strictly scoped to firm
        qs = Task.objects.filter(firm=firm).select_related(
            'client',
            'assigned_to',
            'created_by',
        ).prefetch_related('checklist_items')

        # Current view mode (default: board)
        view_mode = self.request.GET.get('view', 'board').lower()
        if view_mode not in ['board', 'list', 'calendar']:
            view_mode = 'board'

        # Filter parameters
        q = self.request.GET.get('q', '').strip()
        status_filter = self.request.GET.get('status', '').strip()
        priority_filter = self.request.GET.get('priority', '').strip()
        assigned_to_filter = self.request.GET.get('assigned_to', '').strip()
        client_filter = self.request.GET.get('client', '').strip()
        service_filter = self.request.GET.get('service', '').strip()
        overdue_filter = self.request.GET.get('overdue', '').strip()
        recurring_filter = self.request.GET.get('recurring', '').strip()
        due_filter = self.request.GET.get('due', '').strip()

        active_filters_count = 0

        # Search Query
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(client__business_name__icontains=q) |
                Q(client__name__icontains=q) |
                Q(service__icontains=q) |
                Q(assigned_to__first_name__icontains=q) |
                Q(assigned_to__last_name__icontains=q)
            )

        # Filters
        if status_filter:
            qs = qs.filter(status=status_filter)
            active_filters_count += 1

        if priority_filter:
            qs = qs.filter(priority=priority_filter)
            active_filters_count += 1

        if assigned_to_filter:
            if assigned_to_filter == 'unassigned':
                qs = qs.filter(assigned_to__isnull=True)
            elif assigned_to_filter == 'me':
                qs = qs.filter(assigned_to=user)
            else:
                qs = qs.filter(assigned_to_id=assigned_to_filter)
            active_filters_count += 1

        if client_filter:
            qs = qs.filter(client_id=client_filter)
            active_filters_count += 1

        if service_filter:
            qs = qs.filter(service=service_filter)
            active_filters_count += 1

        today = timezone.localdate()

        if overdue_filter == '1':
            qs = qs.filter(due_date__lt=today).exclude(status=Task.Status.COMPLETED)
            active_filters_count += 1

        if recurring_filter == '1':
            qs = qs.filter(is_recurring=True)
            active_filters_count += 1

        if due_filter == 'today':
            qs = qs.filter(due_date=today)
            active_filters_count += 1
        elif due_filter == '7days':
            qs = qs.filter(due_date__gte=today, due_date__lte=today + datetime.timedelta(days=7))
            active_filters_count += 1
        elif due_filter == 'month':
            qs = qs.filter(due_date__gte=today, due_date__lte=today + datetime.timedelta(days=30))
            active_filters_count += 1

        # Global counts across firm (for metric stat ribbon)
        firm_all_tasks = Task.objects.filter(firm=firm)
        pending_count = firm_all_tasks.filter(status=Task.Status.TODO).count()
        in_progress_count = firm_all_tasks.filter(status=Task.Status.IN_PROGRESS).count()
        review_count = firm_all_tasks.filter(status=Task.Status.UNDER_REVIEW).count()
        completed_count = firm_all_tasks.filter(status=Task.Status.COMPLETED).count()
        overdue_count = firm_all_tasks.filter(
            due_date__lt=today
        ).exclude(status=Task.Status.COMPLETED).count()

        # Board columns grouping
        pending_tasks = qs.filter(status=Task.Status.TODO).order_by('due_date', '-priority')
        in_progress_tasks = qs.filter(status=Task.Status.IN_PROGRESS).order_by('due_date', '-priority')
        review_tasks = qs.filter(status=Task.Status.UNDER_REVIEW).order_by('due_date', '-priority')
        completed_tasks = qs.filter(status=Task.Status.COMPLETED).order_by('-completed_at', '-updated_at')

        # List view pagination
        paginator = Paginator(qs.order_by('due_date', '-priority'), 20)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Calendar view grouping (tasks grouped by due_date)
        calendar_days = {}
        if view_mode == 'calendar':
            cal_tasks = qs.exclude(due_date__isnull=True).order_by('due_date')
            for t in cal_tasks:
                date_key = t.due_date.isoformat()
                if date_key not in calendar_days:
                    calendar_days[date_key] = []
                calendar_days[date_key].append(t)

        # Dropdown options
        clients = Client.objects.filter(firm=firm, is_active=True).order_by('business_name', 'name')
        memberships = FirmMembership.objects.filter(
            firm=firm,
            status=MembershipStatus.ACTIVE,
        ).select_related('user')
        staff_members = [m.user for m in memberships if m.user]
        templates = WorkflowTemplate.objects.filter(firm=firm, is_active=True).order_by('title')

        context.update({
            'breadcrumbs': [{'title': 'Tasks', 'url': ''}],
            'current_view': view_mode,
            'current_q': q,
            'current_status': status_filter,
            'current_priority': priority_filter,
            'current_assigned_to': assigned_to_filter,
            'current_client': client_filter,
            'current_service': service_filter,
            'current_overdue': overdue_filter,
            'current_recurring': recurring_filter,
            'current_due': due_filter,
            'active_filters_count': active_filters_count,

            # Counts
            'pending_count': pending_count,
            'in_progress_count': in_progress_count,
            'review_count': review_count,
            'completed_count': completed_count,
            'overdue_count': overdue_count,
            'total_active_count': pending_count + in_progress_count + review_count,

            # Board column task lists
            'pending_tasks': pending_tasks,
            'in_progress_tasks': in_progress_tasks,
            'review_tasks': review_tasks,
            'completed_tasks': completed_tasks,

            # List view pagination
            'page_obj': page_obj,
            'tasks': page_obj.object_list,

            # Calendar view data
            'calendar_days': calendar_days,

            # Metadata & Dropdowns
            'clients': clients,
            'staff_members': staff_members,
            'workflow_templates': templates,
            'service_choices': SERVICE_CHOICES,
            'service_dict': SERVICE_DICT,
            'priority_choices': Task.Priority.choices,
            'status_choices': Task.Status.choices,
            'recurrence_choices': Task.RecurrenceInterval.choices,
            'today': today,

            # Task Creation Form
            'task_form': TaskForm(firm=firm),
            'template_form': WorkflowTemplateForm(),
        })
        return context


class TaskDetailView(PermissionRequiredMixin, TemplateView):
    """
    Comprehensive Task Detail View.
    Strictly verifies User -> Firm -> Task.
    """
    firm_permission = 'view_task'
    template_name = 'tasks/task_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = get_firm_task_or_404(self.request, kwargs['task_id'])
        firm = self.request.firm

        # Related collections
        checklist_items = task.checklist_items.all().order_by('order', 'created_at')
        attachments = task.attachments.all().order_by('-created_at')
        comments = task.comments.all().select_related('user').order_by('created_at')
        activities = task.activities.all().select_related('user').order_by('-created_at')

        # Dropdowns for modals
        memberships = FirmMembership.objects.filter(
            firm=firm,
            status=MembershipStatus.ACTIVE,
        ).select_related('user')
        staff_members = [m.user for m in memberships if m.user]

        context.update({
            'task': task,
            'breadcrumbs': [
                {'title': 'Tasks', 'url': '/tasks/'},
                {'title': task.title, 'url': ''},
            ],
            'checklist_items': checklist_items,
            'attachments': attachments,
            'comments': comments,
            'activities': activities,
            'staff_members': staff_members,
            'service_name': SERVICE_DICT.get(task.service, task.service or 'General Accounting'),
            'today': timezone.localdate(),

            # Forms for interactive actions
            'edit_form': TaskForm(instance=task, firm=firm),
            'comment_form': TaskCommentForm(),
            'attachment_form': TaskAttachmentForm(),
            'checklist_form': TaskChecklistItemForm(),
        })
        return context


class TaskJsonView(PermissionRequiredMixin, View):
    """
    Returns structured JSON for a task to power the interactive slide drawer on the Board view.
    """
    firm_permission = 'view_task'

    def get(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        
        checklist_data = [
            {
                'id': str(item.id),
                'title': item.title,
                'is_completed': item.is_completed,
                'order': item.order,
            }
            for item in task.checklist_items.all().order_by('order', 'created_at')
        ]

        comments_data = [
            {
                'id': str(c.id),
                'user_name': c.user.get_full_name() or c.user.username,
                'initials': c.user.first_name[:1] + c.user.last_name[:1] if c.user.first_name else 'CA',
                'content': c.content,
                'created_at': c.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for c in task.comments.all().select_related('user').order_by('created_at')
        ]

        attachments_data = [
            {
                'id': str(att.id),
                'filename': att.filename,
                'file_url': att.file.url,
                'size': att.formatted_size,
                'created_at': att.created_at.strftime('%Y-%m-%d'),
            }
            for att in task.attachments.all().order_by('-created_at')
        ]

        activities_data = [
            {
                'id': str(act.id),
                'action_type': act.action_type,
                'description': act.description,
                'user_name': act.user.get_full_name() if act.user else 'System',
                'created_at': act.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for act in task.activities.all().select_related('user').order_by('-created_at')[:15]
        ]

        stats = task.checklist_stats

        data = {
            'id': str(task.id),
            'title': task.title,
            'description': task.description,
            'client_name': task.client.business_name or task.client.name if task.client else None,
            'client_id': str(task.client.id) if task.client else None,
            'service': SERVICE_DICT.get(task.service, task.service or 'General Accounting'),
            'service_key': task.service,
            'status': task.status,
            'status_display': task.get_status_display(),
            'status_badge_class': task.status_badge_class,
            'priority': task.priority,
            'priority_display': task.get_priority_display(),
            'priority_badge_class': task.priority_badge_class,
            'start_date': task.start_date.isoformat() if task.start_date else None,
            'due_date': task.due_date.isoformat() if task.due_date else None,
            'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
            'category': task.category or '',
            'is_overdue': task.is_overdue,
            'days_remaining': task.days_remaining,
            'assigned_to_name': task.assigned_to.get_full_name() if task.assigned_to else None,
            'assigned_to_id': str(task.assigned_to.id) if task.assigned_to else None,
            'assigned_to_initials': (task.assigned_to.first_name[:1] + task.assigned_to.last_name[:1]) if task.assigned_to and task.assigned_to.first_name else 'CA',
            'is_recurring': task.is_recurring,
            'recurrence_interval': task.get_recurrence_interval_display(),
            'progress_percent': task.progress_percent,
            'checklist_stats': stats,
            'checklist': checklist_data,
            'comments': comments_data,
            'attachments': attachments_data,
            'activities': activities_data,
            'detail_url': f'/tasks/{task.id}/',
        }
        return JsonResponse(data)


class TaskCreateView(PermissionRequiredMixin, View):
    """
    Handles task creation with:
    - Scoped client, staff, and service
    - Workflow template auto-filling and checklist generation
    - Custom checklist items
    - Recurring schedule support
    - Audit and activity logging
    """
    firm_permission = 'create_task'

    def post(self, request):
        firm = request.firm
        form = TaskForm(request.POST, firm=firm)

        if form.is_valid():
            task = form.save(commit=False)
            task.firm = firm
            task.created_by = request.user
            task.save()

            # 1. Apply Template & Checklist items
            template_id = form.cleaned_data.get('template_id')
            template = None
            if template_id:
                try:
                    template = WorkflowTemplate.objects.get(id=template_id, firm=firm)
                except WorkflowTemplate.DoesNotExist:
                    pass

            # 2. Add raw checklist items from creation wizard
            checklist_raw = request.POST.get('checklist_raw', '').strip()
            items_list = []
            if checklist_raw:
                try:
                    if checklist_raw.startswith('['):
                        items_list = json.loads(checklist_raw)
                    else:
                        items_list = [line.strip() for line in checklist_raw.splitlines() if line.strip()]
                except Exception:
                    pass

            if template:
                # If checklist items were submitted from modal (which pre-filled from template),
                # associate template and populate from items_list without duplicate items.
                if items_list:
                    task.template_applied = template
                    if not task.service and template.service:
                        task.service = template.service
                    task.save(update_fields=['template_applied', 'service', 'updated_at'])
                    for idx, line in enumerate(items_list, start=1):
                        if line:
                            TaskChecklistItem.objects.create(
                                firm=firm,
                                task=task,
                                title=line[:255],
                                order=idx,
                            )
                    record_task_activity(
                        task=task,
                        action_type=TaskActivity.ActionType.CHECKLIST_ADDED,
                        description=f"Applied template '{template.title}' ({len(items_list)} items)",
                        user=request.user,
                    )
                else:
                    apply_template_to_task(task, template, user=request.user)
            elif items_list:
                for idx, line in enumerate(items_list, start=1):
                    if line:
                        TaskChecklistItem.objects.create(
                            firm=firm,
                            task=task,
                            title=line[:255],
                            order=idx,
                        )

            # 3. Notify assignee if assigned
            if task.assigned_to and task.assigned_to != request.user:
                create_notification(
                    recipient=task.assigned_to,
                    firm=firm,
                    title=f"Task Assigned: {task.title}",
                    message=f"{request.user.get_full_name() or request.user.email} assigned '{task.title}' to you. Due: {task.due_date or 'No deadline'}.",
                    notification_type=Notification.NotificationType.TASK,
                    action_url=f"/tasks/{task.id}/",
                )

            # 4. Record Audit and Activity
            record_task_activity(
                task=task,
                action_type=TaskActivity.ActionType.CREATED,
                description=f"Task '{task.title}' created (Priority: {task.get_priority_display()}, Due: {task.due_date or 'No date'})",
                user=request.user,
                request=request,
            )

            messages.success(request, _(f"Task '{task.title}' created successfully."))

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({'success': True, 'task_id': str(task.id), 'redirect_url': '/tasks/'})

            # Check return redirect
            next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/tasks/'
            return redirect(next_url)
        else:
            errors = form.errors.as_text()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _(f"Could not create task: {errors}"))
            return redirect('/tasks/')


class TaskEditView(PermissionRequiredMixin, View):
    """
    Edits an existing task and logs diffs to audit trail.
    """
    firm_permission = 'edit_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        firm = request.firm
        form = TaskForm(request.POST, instance=task, firm=firm)

        old_status = task.status
        old_assigned = task.assigned_to

        if form.is_valid():
            updated_task = form.save()

            changes = []
            if old_status != updated_task.status:
                changes.append(f"Status changed from {old_status} to {updated_task.status}")
                if updated_task.status == Task.Status.COMPLETED and not updated_task.completed_at:
                    updated_task.completed_at = timezone.now()
                    updated_task.save(update_fields=['completed_at'])
            if old_assigned != updated_task.assigned_to:
                changes.append(f"Assigned changed to {updated_task.assigned_to or 'Unassigned'}")

            desc = "; ".join(changes) if changes else "Updated task details"

            record_task_activity(
                task=updated_task,
                action_type=TaskActivity.ActionType.UPDATED,
                description=desc,
                user=request.user,
                request=request,
            )

            messages.success(request, _(f"Task '{updated_task.title}' updated successfully."))

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'task_id': str(updated_task.id)})

            return redirect(f'/tasks/{updated_task.id}/')
        else:
            messages.error(request, _("Please correct errors on the task form."))
            return redirect(f'/tasks/{task.id}/')


class TaskAssignView(PermissionRequiredMixin, View):
    """
    Assigns task to a staff member.
    Verifies assigned user belongs to the active firm.
    """
    firm_permission = 'assign_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        staff_id = request.POST.get('assigned_to', '').strip()

        if staff_id:
            assigned_user = get_object_or_404(
                User.objects.filter(
                    firm_memberships__firm=request.firm,
                    firm_memberships__status=MembershipStatus.ACTIVE,
                    firm_memberships__is_active=True,
                ),
                id=staff_id
            )
            task.assigned_to = assigned_user
            staff_name = assigned_user.get_full_name() or assigned_user.email
        else:
            task.assigned_to = None
            staff_name = "Unassigned"

        task.save(update_fields=['assigned_to', 'updated_at'])

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.ASSIGNED,
            description=f"Task assigned to {staff_name}",
            user=request.user,
            request=request,
        )

        if task.assigned_to and task.assigned_to != request.user:
            create_notification(
                recipient=task.assigned_to,
                firm=request.firm,
                title=f"Task Assigned: {task.title}",
                message=f"{request.user.get_full_name() or request.user.email} assigned task '{task.title}' to you.",
                notification_type=Notification.NotificationType.TASK,
                action_url=f"/tasks/{task.id}/",
            )

        messages.success(request, _(f"Task assigned to {staff_name}."))

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'assigned_to_name': staff_name})

        next_url = request.POST.get('next') or f'/tasks/{task.id}/'
        return redirect(next_url)


class TaskStatusUpdateView(PermissionRequiredMixin, View):
    """
    Instant status update (supports HTML5 drag-and-drop on board and quick status actions).
    """
    firm_permission = 'edit_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        new_status = request.POST.get('status', '').strip().upper()

        valid_statuses = [choice[0] for choice in Task.Status.choices]
        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status code'}, status=400)

        old_status = task.status
        if old_status == new_status:
            return JsonResponse({'success': True, 'unchanged': True})

        task.status = new_status
        if new_status == Task.Status.COMPLETED:
            task.completed_at = timezone.now()
            # If recurring, spawn next iteration
            if task.is_recurring:
                create_next_recurring_task(task, user=request.user)
            notify_user = task.created_by if (task.created_by and task.created_by != request.user) else None
            if notify_user:
                create_notification(
                    recipient=notify_user,
                    firm=request.firm,
                    title=f"Task Completed: {task.title}",
                    message=f"{request.user.get_full_name() or request.user.email} marked '{task.title}' as completed.",
                    notification_type=Notification.NotificationType.TASK,
                    action_url=f"/tasks/{task.id}/",
                )
        else:
            task.completed_at = None

        task.save(update_fields=['status', 'completed_at', 'updated_at'])

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.STATUS_CHANGED,
            description=f"Status advanced from {old_status} to {new_status}",
            user=request.user,
            request=request,
        )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            return JsonResponse({
                'success': True,
                'task_id': str(task.id),
                'new_status': new_status,
                'status_display': task.get_status_display(),
                'status_badge_class': task.status_badge_class,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            })

        messages.success(request, _(f"Status changed to {task.get_status_display()}."))
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/tasks/'
        return redirect(next_url)


class TaskCompleteView(PermissionRequiredMixin, View):
    """
    One-click quick toggle of task completion.
    """
    firm_permission = 'edit_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)

        if task.status == Task.Status.COMPLETED:
            task.status = Task.Status.TODO
            task.completed_at = None
            action_desc = "Reopened task"
            action_type = TaskActivity.ActionType.REOPENED
        else:
            task.status = Task.Status.COMPLETED
            task.completed_at = timezone.now()
            action_desc = "Completed task"
            action_type = TaskActivity.ActionType.COMPLETED
            if task.is_recurring:
                create_next_recurring_task(task, user=request.user)
            notify_user = task.created_by if (task.created_by and task.created_by != request.user) else None
            if notify_user:
                create_notification(
                    recipient=notify_user,
                    firm=request.firm,
                    title=f"Task Completed: {task.title}",
                    message=f"{request.user.get_full_name() or request.user.email} completed task '{task.title}'.",
                    notification_type=Notification.NotificationType.TASK,
                    action_url=f"/tasks/{task.id}/",
                )

        task.save(update_fields=['status', 'completed_at', 'updated_at'])

        record_task_activity(
            task=task,
            action_type=action_type,
            description=action_desc,
            user=request.user,
            request=request,
        )

        messages.success(request, _(f"Task '{task.title}' marked as {task.get_status_display()}."))

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'is_completed': task.status == Task.Status.COMPLETED,
                'status': task.status,
            })

        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/tasks/'
        return redirect(next_url)


class TaskDeleteView(PermissionRequiredMixin, View):
    """
    Deletes task and creates audit trail.
    """
    firm_permission = 'delete_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        task_title = task.title

        log_audit(
            request=request,
            firm=request.firm,
            user=request.user,
            action='DELETE',
            object_type='Task',
            object_id=str(task.id),
            description=f"Deleted task '{task_title}'",
        )

        task.delete()
        messages.success(request, _(f"Task '{task_title}' was permanently deleted."))

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})

        return redirect('/tasks/')


class TaskChecklistAddView(PermissionRequiredMixin, View):
    """
    Adds a new checklist item to a task.
    """
    firm_permission = 'edit_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        title = request.POST.get('title', '').strip()

        if not title:
            return JsonResponse({'success': False, 'error': 'Title required'}, status=400)

        max_order = task.checklist_items.aggregate(models.Max('order'))['order__max'] or 0
        item = TaskChecklistItem.objects.create(
            firm=request.firm,
            task=task,
            title=title,
            order=max_order + 1,
        )

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.CHECKLIST_ADDED,
            description=f"Added checklist step: '{title}'",
            user=request.user,
            request=request,
        )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
            stats = task.checklist_stats
            return JsonResponse({
                'success': True,
                'item': {
                    'id': str(item.id),
                    'title': item.title,
                    'is_completed': item.is_completed,
                    'order': item.order,
                },
                'stats': stats,
            })

        messages.success(request, _("Checklist step added."))
        return redirect(f'/tasks/{task.id}/')


class TaskChecklistToggleView(PermissionRequiredMixin, View):
    """
    Toggles a checklist item complete / incomplete.
    """
    firm_permission = 'edit_task'

    def post(self, request, item_id):
        item = get_object_or_404(
            TaskChecklistItem.objects.filter(firm=request.firm).select_related('task'),
            id=item_id,
        )
        task = item.task

        item.is_completed = not item.is_completed
        if item.is_completed:
            item.completed_at = timezone.now()
            item.completed_by = request.user
        else:
            item.completed_at = None
            item.completed_by = None
        item.save()

        stats = task.checklist_stats

        # If all checklist items completed, auto-advance or suggest review
        if stats['total'] > 0 and stats['completed'] == stats['total']:
            if task.status in [Task.Status.TODO, Task.Status.IN_PROGRESS]:
                task.status = Task.Status.UNDER_REVIEW
                task.save(update_fields=['status', 'updated_at'])
                record_task_activity(
                    task=task,
                    action_type=TaskActivity.ActionType.STATUS_CHANGED,
                    description="All checklist items verified. Advanced to Partner Review.",
                    user=request.user,
                    request=request,
                )

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.CHECKLIST_TOGGLED,
            description=f"{'Completed' if item.is_completed else 'Unchecked'} checklist item: '{item.title}'",
            user=request.user,
            request=request,
        )

        return JsonResponse({
            'success': True,
            'is_completed': item.is_completed,
            'stats': stats,
            'task_status': task.status,
            'task_status_display': task.get_status_display(),
        })


class TaskChecklistDeleteView(PermissionRequiredMixin, View):
    """
    Deletes a checklist item.
    """
    firm_permission = 'edit_task'

    def post(self, request, item_id):
        item = get_object_or_404(
            TaskChecklistItem.objects.filter(firm=request.firm).select_related('task'),
            id=item_id,
        )
        task = item.task
        item_title = item.title
        item.delete()

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.CHECKLIST_DELETED,
            description=f"Removed checklist step: '{item_title}'",
            user=request.user,
            request=request,
        )

        stats = task.checklist_stats

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'stats': stats})

        messages.success(request, _("Checklist item removed."))
        return redirect(f'/tasks/{task.id}/')


class TaskAttachDocumentView(PermissionRequiredMixin, View):
    """
    Uploads an attachment file to a task.
    """
    firm_permission = 'upload_document'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        uploaded_file = request.FILES.get('file')

        if not uploaded_file:
            messages.error(request, _("Please choose a file to upload."))
            return redirect(f'/tasks/{task.id}/')

        attachment = TaskAttachment.objects.create(
            firm=request.firm,
            task=task,
            file=uploaded_file,
            filename=uploaded_file.name,
            file_size_bytes=uploaded_file.size,
            uploaded_by=request.user,
        )

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.ATTACHMENT_ADDED,
            description=f"Attached file '{uploaded_file.name}' ({attachment.formatted_size})",
            user=request.user,
            request=request,
        )

        messages.success(request, _(f"File '{uploaded_file.name}' attached successfully."))
        return redirect(f'/tasks/{task.id}/')


class TaskCommentCreateView(PermissionRequiredMixin, View):
    """
    Adds a comment to a task discussion thread.
    """
    firm_permission = 'view_task'

    def post(self, request, task_id):
        task = get_firm_task_or_404(request, task_id)
        content = request.POST.get('content', '').strip()

        if not content:
            messages.error(request, _("Comment cannot be empty."))
            return redirect(f'/tasks/{task.id}/')

        comment = TaskComment.objects.create(
            firm=request.firm,
            task=task,
            user=request.user,
            content=content,
        )

        record_task_activity(
            task=task,
            action_type=TaskActivity.ActionType.COMMENT_ADDED,
            description=f"Added note: '{content[:60]}...'",
            user=request.user,
            request=request,
        )

        # Notify task assigned user and creator (excluding commenter)
        recipients = set()
        if task.assigned_to and task.assigned_to != request.user:
            recipients.add(task.assigned_to)
        if task.created_by and task.created_by != request.user:
            recipients.add(task.created_by)
        for rec in recipients:
            create_notification(
                recipient=rec,
                firm=request.firm,
                title=f"New comment on '{task.title}'",
                message=f"{request.user.get_full_name() or request.user.email}: {content[:100]}",
                notification_type=Notification.NotificationType.TASK,
                action_url=f"/tasks/{task.id}/",
            )

        messages.success(request, _("Comment posted."))

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'comment': {
                    'id': str(comment.id),
                    'user_name': request.user.get_full_name() or request.user.username,
                    'initials': request.user.first_name[:1] + request.user.last_name[:1] if request.user.first_name else 'CA',
                    'content': comment.content,
                    'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
                }
            })

        return redirect(f'/tasks/{task.id}/')


class WorkflowTemplateListView(FirmRequiredMixin, TemplateView):
    """
    Workflow Templates management view.
    """
    template_name = 'tasks/template_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm
        ensure_firm_workflow_templates(firm, user=self.request.user)

        templates = WorkflowTemplate.objects.filter(firm=firm, is_active=True).prefetch_related('items')

        context.update({
            'breadcrumbs': [
                {'title': 'Tasks', 'url': '/tasks/'},
                {'title': 'Workflow Templates', 'url': ''},
            ],
            'templates': templates,
            'form': WorkflowTemplateForm(),
            'service_choices': SERVICE_CHOICES,
            'service_dict': SERVICE_DICT,
        })
        return context


class WorkflowTemplateCreateView(FirmRequiredMixin, View):
    """
    Creates a new reusable workflow template with checklist steps.
    """
    def post(self, request):
        firm = request.firm
        form = WorkflowTemplateForm(request.POST)

        if form.is_valid():
            template = form.save(commit=False)
            template.firm = firm
            template.created_by = request.user
            template.save()

            lines = form.cleaned_data['checklist_lines'].splitlines()
            for idx, line in enumerate(lines, start=1):
                clean_line = line.strip()
                if clean_line:
                    WorkflowTemplateItem.objects.create(
                        template=template,
                        title=clean_line,
                        order=idx,
                    )

            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='CREATE',
                object_type='WorkflowTemplate',
                object_id=str(template.id),
                description=f"Created workflow template '{template.title}' with {len(lines)} steps",
            )

            messages.success(request, _(f"Workflow template '{template.title}' created successfully."))

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'template_id': str(template.id)})

            return redirect('/tasks/templates/')
        else:
            messages.error(request, _("Please correct errors in template creation."))
            return redirect('/tasks/templates/')


class WorkflowTemplateDeleteView(FirmRequiredMixin, View):
    """
    Deletes a custom workflow template.
    """
    def post(self, request, template_id):
        template = get_object_or_404(WorkflowTemplate.objects.filter(firm=request.firm), id=template_id)
        title = template.title
        template.delete()

        log_audit(
            request=request,
            firm=request.firm,
            user=request.user,
            action='DELETE',
            object_type='WorkflowTemplate',
            object_id=str(template_id),
            description=f"Deleted workflow template '{title}'",
        )

        messages.success(request, _(f"Workflow template '{title}' removed."))
        return redirect('/tasks/templates/')
