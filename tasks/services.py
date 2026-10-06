import datetime
from django.utils import timezone
from audit.services import log_audit
from clients.models import ClientActivity
from tasks.models import (
    Task,
    TaskActivity,
    TaskChecklistItem,
    WorkflowTemplate,
    WorkflowTemplateItem,
)


DEFAULT_TEMPLATES = [
    {
        'title': 'Monthly VAT Workflow',
        'description': 'Standard monthly Value Added Tax verification, reconciliation, and IRD portal return filing.',
        'service': 'TAX_VAT',
        'default_priority': 'HIGH',
        'estimated_days': 5,
        'checklist': [
            'Request documents',
            'Receive sales data',
            'Receive purchase data',
            'Review documents',
            'Prepare working papers',
            'CA review',
            'Finalize',
            'Notify client',
        ],
    },
    {
        'title': 'Quarterly TDS Reconciliation & Withholding',
        'description': 'Quarterly reconciliation of Section 87/88/88A/89 withholdings with ETDS portal submissions.',
        'service': 'TDS_WITHHOLDING',
        'default_priority': 'HIGH',
        'estimated_days': 7,
        'checklist': [
            'Download ETDS ledger from IRD portal',
            'Obtain vendor invoice register and payment vouchers',
            'Cross-verify tax deductions with TDS certificates',
            'Reconcile variances with client accountant',
            'Generate quarterly withholding tax report',
            'Manager review & approval',
            'Final submission and client intimation',
        ],
    },
    {
        'title': 'Annual Statutory Audit (NFRS/NAS)',
        'description': 'End-to-end statutory audit engagement conforming to Nepal Standards on Auditing (NSA).',
        'service': 'STATUTORY_AUDIT',
        'default_priority': 'URGENT',
        'estimated_days': 21,
        'checklist': [
            'Engagement letter & independence confirmation',
            'Opening balance & prior audit report scrutiny',
            'Trial balance & general ledger scrutiny',
            'Bank balance & loan confirmation audit',
            'Fixed asset physical verification check',
            'Revenue recognition & VAT matching test',
            'Trade receivables and aging scrutiny',
            'Statutory compliance & tax liability review',
            'Preparation of draft financial statements (NFRS)',
            'Engagement Partner / CA review and audit queries',
            'Issue Audit Report & Management Letter',
        ],
    },
    {
        'title': 'OCR Company Registrar Annual Return',
        'description': 'Office of the Company Registrar (OCR) compliance and annual corporate returns.',
        'service': 'OCR_COMPLIANCE',
        'default_priority': 'MEDIUM',
        'estimated_days': 10,
        'checklist': [
            'Obtain AGM notice, agenda and director register',
            'Inspect minute book and statutory records',
            'Prepare OCR Schedule & Form 21 declarations',
            'Upload audited balance sheet to OCR portal',
            'Pay annual registration fee & retrieve receipt',
        ],
    },
]


def ensure_firm_workflow_templates(firm, user=None):
    """
    Ensures the firm has standard CA workflow templates pre-seeded.
    """
    created_templates = []
    for tpl_data in DEFAULT_TEMPLATES:
        template, created = WorkflowTemplate.objects.get_or_create(
            firm=firm,
            title=tpl_data['title'],
            defaults={
                'description': tpl_data['description'],
                'service': tpl_data['service'],
                'default_priority': tpl_data['default_priority'],
                'estimated_days': tpl_data['estimated_days'],
                'is_system': True,
                'created_by': user,
            },
        )
        if created:
            for idx, item_title in enumerate(tpl_data['checklist'], start=1):
                WorkflowTemplateItem.objects.create(
                    template=template,
                    title=item_title,
                    order=idx,
                )
            created_templates.append(template)
    return created_templates


def apply_template_to_task(task, template, user=None):
    """
    Copies items from a WorkflowTemplate to a Task as TaskChecklistItems.
    """
    task.template_applied = template
    if not task.service and template.service:
        task.service = template.service
    task.save(update_fields=['template_applied', 'service', 'updated_at'])

    items = template.items.all().order_by('order')
    for item in items:
        TaskChecklistItem.objects.create(
            firm=task.firm,
            task=task,
            title=item.title,
            order=item.order,
        )

    record_task_activity(
        task=task,
        action_type=TaskActivity.ActionType.CHECKLIST_ADDED,
        description=f"Applied template '{template.title}' ({items.count()} items)",
        user=user,
    )


def record_task_activity(task, action_type, description, user=None, request=None):
    """
    Records both a TaskActivity (for detail stream) and AuditLog (for firm compliance audit).
    Also updates ClientActivity if task has an associated client.
    """
    # 1. TaskActivity
    activity = TaskActivity.objects.create(
        firm=task.firm,
        task=task,
        action_type=action_type,
        description=description,
        user=user,
    )

    # 2. AuditLog
    log_audit(
        request=request,
        firm=task.firm,
        user=user,
        action=action_type,
        object_type='Task',
        object_id=str(task.id),
        description=f"Task '{task.title}': {description}",
    )

    # 3. ClientActivity if relevant
    if task.client:
        client_act_type = ClientActivity.ActivityType.TASK_CREATED if action_type == TaskActivity.ActionType.CREATED \
            else (ClientActivity.ActivityType.TASK_COMPLETED if action_type == TaskActivity.ActionType.COMPLETED else None)
        if client_act_type:
            ClientActivity.objects.create(
                firm=task.firm,
                client=task.client,
                activity_type=client_act_type,
                description=f"Task: {task.title} - {description}",
                performed_by=user,
            )

    return activity


def create_next_recurring_task(task, user=None):
    """
    If task is recurring, creates the next instance with shifted due date.
    """
    if not task.is_recurring or not task.due_date:
        return None

    interval = task.recurrence_interval
    base_date = task.due_date

    if interval == Task.RecurrenceInterval.DAILY:
        next_due = base_date + datetime.timedelta(days=1)
    elif interval == Task.RecurrenceInterval.WEEKLY:
        next_due = base_date + datetime.timedelta(weeks=1)
    elif interval == Task.RecurrenceInterval.MONTHLY:
        # Approximate 1 month ahead
        year = base_date.year + (base_date.month // 12)
        month = (base_date.month % 12) + 1
        day = min(base_date.day, 28)
        next_due = datetime.date(year, month, day)
    elif interval == Task.RecurrenceInterval.QUARTERLY:
        # 3 months ahead
        month_idx = base_date.month + 3
        year = base_date.year + ((month_idx - 1) // 12)
        month = ((month_idx - 1) % 12) + 1
        day = min(base_date.day, 28)
        next_due = datetime.date(year, month, day)
    elif interval == Task.RecurrenceInterval.YEARLY:
        next_due = datetime.date(base_date.year + 1, base_date.month, min(base_date.day, 28))
    elif interval == Task.RecurrenceInterval.CUSTOM and task.custom_recurrence_days:
        next_due = base_date + datetime.timedelta(days=task.custom_recurrence_days)
    else:
        return None

    if task.recurrence_end_date and next_due > task.recurrence_end_date:
        return None

    # Guard against generating duplicate recurring tasks
    existing = Task.objects.filter(
        firm=task.firm,
        client=task.client,
        title=task.title,
        due_date=next_due,
        is_recurring=True,
    ).first()
    if existing:
        return existing

    # Create next task
    next_task = Task.objects.create(
        firm=task.firm,
        title=task.title,
        description=task.description,
        client=task.client,
        service=task.service,
        category=task.category,
        estimated_hours=task.estimated_hours,
        assigned_to=task.assigned_to,
        created_by=user or task.created_by,
        priority=task.priority,
        status=Task.Status.TODO,
        due_date=next_due,
        is_recurring=True,
        recurrence_interval=task.recurrence_interval,
        custom_recurrence_days=task.custom_recurrence_days,
        recurrence_end_date=task.recurrence_end_date,
        template_applied=task.template_applied,
    )

    # Replicate checklist items if template or items existed
    for item in task.checklist_items.all().order_by('order'):
        TaskChecklistItem.objects.create(
            firm=task.firm,
            task=next_task,
            title=item.title,
            order=item.order,
            is_completed=False,
        )

    record_task_activity(
        task=next_task,
        action_type=TaskActivity.ActionType.CREATED,
        description=f"Auto-generated recurring task for {next_due}",
        user=user,
    )

    return next_task
