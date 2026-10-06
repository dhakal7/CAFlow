import datetime
import logging
from django.utils import timezone
from django.db import models
from django.db.models import Q

from audit.services import log_audit
from notifications.models import Notification
from notifications.services import create_notification
from compliance.models import (
    ComplianceDeadline,
    ComplianceType,
    ClientComplianceRequirement,
    ComplianceActivity,
)

logger = logging.getLogger(__name__)

DEFAULT_COMPLIANCE_TYPES = [
    {
        'name': 'Monthly VAT Return & E-Filing',
        'code': 'VAT_MONTHLY',
        'category': ComplianceType.Category.VAT,
        'statutory_authority': 'Inland Revenue Department (IRD)',
        'frequency': ComplianceType.Frequency.MONTHLY,
        'default_priority': 'URGENT',
        'due_day_bs': 25,
        'description': 'Mandatory monthly Annex 5, 6, 7 submission and VAT payment on IRD portal per Section 17 & 19 of VAT Act 2052.',
        'penalty_guidelines': '0.1% per day penalty on overdue returns plus 15% interest on unpaid tax.',
    },
    {
        'name': 'Withholding Tax (TDS / E-TDS) Monthly E-Return',
        'code': 'TDS_MONTHLY',
        'category': ComplianceType.Category.TDS,
        'statutory_authority': 'Inland Revenue Department (IRD)',
        'frequency': ComplianceType.Frequency.MONTHLY,
        'default_priority': 'HIGH',
        'due_day_bs': 25,
        'description': 'Withholding tax certificate reconciliation and E-TDS portal return filing under Section 90 of Income Tax Act 2058.',
        'penalty_guidelines': '15% per annum interest and Section 120 statutory late-filing fee.',
    },
    {
        'name': 'Advance Income Tax Installment (Q1 40% / Q2 70% / Q3 100%)',
        'code': 'INCOME_TAX_ADVANCE',
        'category': ComplianceType.Category.INCOME_TAX,
        'statutory_authority': 'Inland Revenue Department (IRD)',
        'frequency': ComplianceType.Frequency.TRIANNUAL,
        'default_priority': 'URGENT',
        'due_day_bs': 30,
        'description': 'Estimated tax calculation and installment payments due end of Poush (40%), Chaitra (70%), and Ashad (100%) per Section 94.',
        'penalty_guidelines': 'Interest under Section 118 at 15% p.a. on shortfall of estimated liability.',
    },
    {
        'name': 'Annual Corporate Income Tax Return (D-03 Filing)',
        'code': 'INCOME_TAX_ANNUAL_D03',
        'category': ComplianceType.Category.INCOME_TAX,
        'statutory_authority': 'Inland Revenue Department (IRD)',
        'frequency': ComplianceType.Frequency.ANNUAL,
        'default_priority': 'URGENT',
        'due_day_bs': 30,
        'description': 'Final audited taxable income reconciliation and D-03 return submission under Section 96 of Income Tax Act 2058 (due within 3 months of fiscal year close).',
        'penalty_guidelines': 'Penalty of Rs 100 per month or 0.1% of turnover plus interest under Section 117/119.',
    },
    {
        'name': 'Company Registrar (OCR) D-01 Annual Returns & AGM Filing',
        'code': 'OCR_ANNUAL_D01',
        'category': ComplianceType.Category.COMPANIES_ACT,
        'statutory_authority': 'Office of Company Registrar (OCR)',
        'frequency': ComplianceType.Frequency.ANNUAL,
        'default_priority': 'HIGH',
        'due_day_bs': 29,
        'description': 'Filing of audited balance sheet, auditor report, share register, and AGM minutes with OCR under Section 51 & 80 of Companies Act 2063.',
        'penalty_guidelines': 'Late fee slabs from Rs 1,000 to Rs 20,000 based on authorized capital.',
    },
    {
        'name': 'Social Security Fund (SSF) Monthly Contribution',
        'code': 'SSF_PAYROLL',
        'category': ComplianceType.Category.LABOUR_ACT,
        'statutory_authority': 'Social Security Fund (SSF)',
        'frequency': ComplianceType.Frequency.MONTHLY,
        'default_priority': 'MEDIUM',
        'due_day_bs': 30,
        'description': 'Monthly payroll contribution (20% Employer + 11% Employee = 31%) deposit on SSF portal under Labour Act 2074 & SSF Rules.',
        'penalty_guidelines': '10% late surcharge on delayed contribution deposits.',
    },
    {
        'name': 'Annual Statutory Audit & UDIN Compliance',
        'code': 'STATUTORY_AUDIT',
        'category': ComplianceType.Category.ICAN_ACT,
        'statutory_authority': 'Institute of Chartered Accountants of Nepal (ICAN)',
        'frequency': ComplianceType.Frequency.ANNUAL,
        'default_priority': 'URGENT',
        'due_day_bs': 30,
        'description': 'Finalization of statutory audit working papers, auditor report issuance, and mandatory ICAN UDIN generation.',
        'penalty_guidelines': 'Mandatory for statutory audit validity; non-UDIN reports invalid under ICAN directives.',
    },
    {
        'name': 'Excise Duty Monthly Return',
        'code': 'EXCISE_MONTHLY',
        'category': ComplianceType.Category.OTHER,
        'statutory_authority': 'Inland Revenue Department (IRD)',
        'frequency': ComplianceType.Frequency.MONTHLY,
        'default_priority': 'MEDIUM',
        'due_day_bs': 25,
        'description': 'Monthly production register, dispatch slips, and excise payment verification under Excise Act 2058.',
        'penalty_guidelines': 'Fines and cancellation of excise license per Excise Rules.',
    },
]


def ensure_default_compliance_types(firm, user=None):
    """
    Seeds default statutory compliance types for the CA firm if they do not exist.
    Strictly tenant-scoped.
    """
    if not firm:
        return []

    types_created = []
    for item in DEFAULT_COMPLIANCE_TYPES:
        comp_type, created = ComplianceType.objects.get_or_create(
            firm=firm,
            name=item['name'],
            defaults={
                'code': item['code'],
                'category': item['category'],
                'statutory_authority': item['statutory_authority'],
                'frequency': item['frequency'],
                'default_priority': item['default_priority'],
                'due_day_bs': item['due_day_bs'],
                'description': item['description'],
                'penalty_guidelines': item['penalty_guidelines'],
                'is_active': True,
                'is_system_default': True,
            }
        )
        if created:
            types_created.append(comp_type)
    return types_created


def get_compliance_dashboard_metrics(firm):
    """
    Calculates compliance dashboard metrics for the given firm:
    - due today
    - due this week
    - overdue
    - waiting for client
    - awaiting review
    - completed
    - in progress
    - upcoming
    """
    if not firm:
        return {
            'due_today': 0,
            'due_this_week': 0,
            'overdue': 0,
            'waiting_for_client': 0,
            'awaiting_review': 0,
            'completed': 0,
            'in_progress': 0,
            'upcoming': 0,
            'total_active': 0,
        }

    today = timezone.localdate()
    week_end = today + datetime.timedelta(days=7)

    qs = ComplianceDeadline.objects.filter(firm=firm)

    # Active items exclude completed, filed, cancelled
    active_qs = qs.exclude(status__in=[
        ComplianceDeadline.Status.COMPLETED,
        ComplianceDeadline.Status.FILED,
        ComplianceDeadline.Status.CANCELLED,
    ])

    due_today = active_qs.filter(due_date_ad=today).count()
    due_this_week = active_qs.filter(due_date_ad__gte=today, due_date_ad__lte=week_end).count()

    # Overdue includes explicit OVERDUE status or due_date in past
    overdue = qs.filter(
        Q(status=ComplianceDeadline.Status.OVERDUE) |
        (Q(due_date_ad__lt=today) & ~Q(status__in=[
            ComplianceDeadline.Status.COMPLETED,
            ComplianceDeadline.Status.FILED,
            ComplianceDeadline.Status.CANCELLED,
        ]))
    ).distinct().count()

    waiting_for_client = qs.filter(status=ComplianceDeadline.Status.WAITING_FOR_CLIENT).count()
    awaiting_review = qs.filter(status=ComplianceDeadline.Status.READY_FOR_REVIEW).count()
    completed = qs.filter(status__in=[ComplianceDeadline.Status.COMPLETED, ComplianceDeadline.Status.FILED]).count()
    in_progress = qs.filter(status=ComplianceDeadline.Status.IN_PROGRESS).count()
    upcoming = qs.filter(status=ComplianceDeadline.Status.UPCOMING).count()
    total_active = active_qs.count()

    return {
        'due_today': due_today,
        'due_this_week': due_this_week,
        'overdue': overdue,
        'waiting_for_client': waiting_for_client,
        'awaiting_review': awaiting_review,
        'completed': completed,
        'in_progress': in_progress,
        'upcoming': upcoming,
        'total_active': total_active,
    }


def check_and_update_overdue_deadlines(firm=None):
    """
    Automatically identifies items where due date has passed and marks them OVERDUE.
    Dispatches notifications to assigned staff and reviewers.
    """
    today = timezone.localdate()
    qs = ComplianceDeadline.objects.all()
    if firm:
        qs = qs.filter(firm=firm)

    pending_past_due = qs.filter(
        due_date_ad__lt=today
    ).exclude(
        status__in=[
            ComplianceDeadline.Status.OVERDUE,
            ComplianceDeadline.Status.COMPLETED,
            ComplianceDeadline.Status.FILED,
            ComplianceDeadline.Status.CANCELLED,
        ]
    )

    updated_count = 0
    for deadline in pending_past_due:
        old_status = deadline.status
        deadline.status = ComplianceDeadline.Status.OVERDUE
        deadline.save(update_fields=['status', 'updated_at'])
        updated_count += 1

        # Activity log
        ComplianceActivity.objects.create(
            firm=deadline.firm,
            deadline=deadline,
            action='AUTO_MARKED_OVERDUE',
            from_status=old_status,
            to_status=ComplianceDeadline.Status.OVERDUE,
            description=f"Statutory filing date {deadline.due_date_ad} (BS {deadline.due_date_bs}) elapsed. Identified as overdue.",
        )

        # Notify assigned staff
        if deadline.assigned_to:
            create_notification(
                recipient=deadline.assigned_to,
                firm=deadline.firm,
                title=f"OVERDUE: {deadline.title}",
                message=f"Compliance deadline for {deadline.client.name if deadline.client else 'General'} was due on {deadline.due_date_ad} (BS {deadline.due_date_bs}) and is now OVERDUE.",
                notification_type=Notification.NotificationType.COMPLIANCE,
                action_url=f"/compliance/?id={deadline.id}",
            )

        # Notify reviewer if assigned
        if deadline.reviewer and deadline.reviewer != deadline.assigned_to:
            create_notification(
                recipient=deadline.reviewer,
                firm=deadline.firm,
                title=f"OVERDUE ALERT: {deadline.title}",
                message=f"Compliance deadline for {deadline.client.name if deadline.client else 'General'} is overdue. Review or follow-up required.",
                notification_type=Notification.NotificationType.COMPLIANCE,
                action_url=f"/compliance/?id={deadline.id}",
            )

    return updated_count


def transition_compliance_status(deadline, new_status, user=None, request=None, notes='', filing_reference_number='', completion_date=None):
    """
    Validates and performs a workflow transition on a compliance deadline:
    Deadline -> Preparation -> Documents -> Review -> Filing -> Completed.
    Records ComplianceActivity, AuditLog, and dispatches in-app notifications.
    """
    old_status = deadline.status
    if old_status == new_status and not notes and not filing_reference_number:
        return deadline

    deadline.status = new_status
    update_fields = ['status', 'updated_at']

    if notes:
        deadline.notes = f"{deadline.notes}\n[{timezone.localdate()}] {notes}".strip() if deadline.notes else notes
        update_fields.append('notes')

    if filing_reference_number:
        deadline.filing_reference_number = filing_reference_number
        update_fields.append('filing_reference_number')

    if new_status == ComplianceDeadline.Status.COMPLETED:
        deadline.completion_date = completion_date or timezone.localdate()
        update_fields.append('completion_date')
    elif new_status == ComplianceDeadline.Status.FILED and not deadline.completion_date and completion_date:
        deadline.completion_date = completion_date
        update_fields.append('completion_date')

    deadline.save(update_fields=update_fields)

    # 1. Record immutable ComplianceActivity
    ComplianceActivity.objects.create(
        firm=deadline.firm,
        deadline=deadline,
        action=f"STATUS_{new_status}",
        from_status=old_status,
        to_status=new_status,
        description=notes or f"Transitioned filing status from {old_status} to {new_status}",
        performed_by=user,
    )

    # 2. Record AuditLog
    log_audit(
        request=request,
        firm=deadline.firm,
        user=user,
        action='UPDATE_STATUS',
        object_type='ComplianceDeadline',
        object_id=str(deadline.id),
        description=f"Compliance '{deadline.title}' transitioned to {new_status}. {notes}",
    )

    # 3. Dispatches notifications based on workflow step
    client_name = deadline.client.name if deadline.client else "Firm General"

    if new_status == ComplianceDeadline.Status.READY_FOR_REVIEW:
        # Staff submitted for review: notify reviewer
        if deadline.reviewer:
            create_notification(
                recipient=deadline.reviewer,
                firm=deadline.firm,
                title=f"Review Required: {deadline.title}",
                message=f"Filing draft for {client_name} ({deadline.period or deadline.due_date_bs}) has been submitted by {user.get_full_name() if user else 'staff'} and is ready for your review.",
                notification_type=Notification.NotificationType.COMPLIANCE,
                action_url=f"/compliance/?id={deadline.id}",
            )
    elif new_status == ComplianceDeadline.Status.FILED:
        # Filed: notify reviewer and assigned staff
        targets = {deadline.assigned_to, deadline.reviewer} - {None, user}
        for recipient in targets:
            create_notification(
                recipient=recipient,
                firm=deadline.firm,
                title=f"Filed: {deadline.title}",
                message=f"Compliance filing for {client_name} marked as filed (Ref: {deadline.filing_reference_number or 'N/A'}).",
                notification_type=Notification.NotificationType.COMPLIANCE,
                action_url=f"/compliance/?id={deadline.id}",
            )
    elif new_status == ComplianceDeadline.Status.COMPLETED:
        # Completed: if recurring, schedule next period deadline
        if deadline.is_recurring:
            create_next_recurring_deadline(deadline, user=user)

        targets = {deadline.assigned_to, deadline.reviewer} - {None, user}
        for recipient in targets:
            create_notification(
                recipient=recipient,
                firm=deadline.firm,
                title=f"Completed: {deadline.title}",
                message=f"Compliance filing for {client_name} ({deadline.period or deadline.due_date_bs}) is marked as fully completed.",
                notification_type=Notification.NotificationType.COMPLIANCE,
                action_url=f"/compliance/?id={deadline.id}",
            )

    return deadline


def create_next_recurring_deadline(deadline, user=None):
    """
    If a compliance deadline is recurring, computes the next period and due date,
    and creates the successor ComplianceDeadline record.
    Prevents duplicate generation for the same period.
    """
    if not deadline.is_recurring or not deadline.due_date_ad:
        return None

    freq = deadline.recurrence_frequency
    base_date = deadline.due_date_ad

    # Determine shift in Gregorian date
    if freq == ComplianceDeadline.RecurrenceFrequency.MONTHLY:
        year = base_date.year + (base_date.month // 12)
        month = (base_date.month % 12) + 1
        day = min(base_date.day, 28)
        next_due_ad = datetime.date(year, month, day)
    elif freq == ComplianceDeadline.RecurrenceFrequency.QUARTERLY:
        month_idx = base_date.month + 3
        year = base_date.year + ((month_idx - 1) // 12)
        month = ((month_idx - 1) % 12) + 1
        day = min(base_date.day, 28)
        next_due_ad = datetime.date(year, month, day)
    elif freq == ComplianceDeadline.RecurrenceFrequency.TRIANNUAL:
        month_idx = base_date.month + 4
        year = base_date.year + ((month_idx - 1) // 12)
        month = ((month_idx - 1) % 12) + 1
        day = min(base_date.day, 28)
        next_due_ad = datetime.date(year, month, day)
    elif freq == ComplianceDeadline.RecurrenceFrequency.BIANNUAL:
        month_idx = base_date.month + 6
        year = base_date.year + ((month_idx - 1) // 12)
        month = ((month_idx - 1) % 12) + 1
        day = min(base_date.day, 28)
        next_due_ad = datetime.date(year, month, day)
    elif freq == ComplianceDeadline.RecurrenceFrequency.ANNUAL:
        next_due_ad = datetime.date(base_date.year + 1, base_date.month, min(base_date.day, 28))
    else:
        return None

    if deadline.recurrence_end_date and next_due_ad > deadline.recurrence_end_date:
        return None

    # Compute approximate next Bikram Sambat date string
    next_due_bs = ""
    if deadline.due_date_bs and '-' in deadline.due_date_bs:
        try:
            parts = deadline.due_date_bs.split('-')
            bs_yr, bs_mo, bs_dy = int(parts[0]), int(parts[1]), int(parts[2][:2])
            if freq == ComplianceDeadline.RecurrenceFrequency.MONTHLY:
                bs_mo += 1
                if bs_mo > 12:
                    bs_mo = 1
                    bs_yr += 1
            elif freq == ComplianceDeadline.RecurrenceFrequency.QUARTERLY:
                bs_mo += 3
                if bs_mo > 12:
                    bs_mo -= 12
                    bs_yr += 1
            elif freq == ComplianceDeadline.RecurrenceFrequency.TRIANNUAL:
                bs_mo += 4
                if bs_mo > 12:
                    bs_mo -= 12
                    bs_yr += 1
            elif freq == ComplianceDeadline.RecurrenceFrequency.BIANNUAL:
                bs_mo += 6
                if bs_mo > 12:
                    bs_mo -= 12
                    bs_yr += 1
            elif freq == ComplianceDeadline.RecurrenceFrequency.ANNUAL:
                bs_yr += 1
            next_due_bs = f"{bs_yr:04d}-{bs_mo:02d}-{bs_dy:02d}"
        except Exception:
            next_due_bs = deadline.due_date_bs
    else:
        next_due_bs = deadline.due_date_bs

    # Guard against duplicate deadline creation
    existing = ComplianceDeadline.objects.filter(
        firm=deadline.firm,
        client=deadline.client,
        title=deadline.title,
        due_date_ad=next_due_ad,
    ).first()
    if existing:
        return existing

    next_deadline = ComplianceDeadline.objects.create(
        firm=deadline.firm,
        client=deadline.client,
        compliance_type=deadline.compliance_type,
        governing_act=deadline.governing_act,
        title=deadline.title,
        description=deadline.description,
        period=f"Next Cycle ({next_due_bs})" if not deadline.period else f"Next {deadline.period}",
        due_date_bs=next_due_bs,
        due_date_ad=next_due_ad,
        assigned_to=deadline.assigned_to,
        reviewer=deadline.reviewer,
        priority=deadline.priority,
        status=ComplianceDeadline.Status.UPCOMING,
        notes=deadline.notes,
        is_recurring=True,
        recurrence_frequency=deadline.recurrence_frequency,
        recurrence_end_date=deadline.recurrence_end_date,
    )

    ComplianceActivity.objects.create(
        firm=deadline.firm,
        deadline=next_deadline,
        action='AUTO_RECURRING_SPAWNED',
        from_status='',
        to_status=ComplianceDeadline.Status.UPCOMING,
        description=f"Auto-generated recurring successor deadline from completed cycle {deadline.id}.",
        performed_by=user,
    )

    if next_deadline.assigned_to:
        create_notification(
            recipient=next_deadline.assigned_to,
            firm=next_deadline.firm,
            title=f"Upcoming Compliance: {next_deadline.title}",
            message=f"New recurring compliance schedule created for {next_deadline.client.name if next_deadline.client else 'General'} due on BS {next_deadline.due_date_bs}.",
            notification_type=Notification.NotificationType.COMPLIANCE,
            action_url=f"/compliance/?id={next_deadline.id}",
        )

    return next_deadline


def generate_deadlines_from_client_requirements(firm, target_period_name="", due_date_bs="", due_date_ad=None, user=None):
    """
    Generates compliance deadline items for all active client subscriptions of the specified firm.
    Supports requirement: 'Support recurring compliance schedules... Do not assume every client has every compliance requirement.'
    """
    if not firm or not due_date_ad:
        return []

    requirements = ClientComplianceRequirement.objects.filter(
        firm=firm,
        is_active=True,
        client__is_active=True,
    ).select_related('client', 'compliance_type', 'assigned_staff', 'reviewer')

    created_deadlines = []
    for req in requirements:
        ctype = req.compliance_type
        # Check if already exists
        exists = ComplianceDeadline.objects.filter(
            firm=firm,
            client=req.client,
            compliance_type=ctype,
            due_date_ad=due_date_ad,
        ).exists()
        if exists:
            continue

        deadline = ComplianceDeadline.objects.create(
            firm=firm,
            client=req.client,
            compliance_type=ctype,
            governing_act=ctype.category,
            title=f"{ctype.name} ({req.client.name})",
            description=ctype.description,
            period=target_period_name,
            due_date_bs=due_date_bs or (f"BS Due Day {ctype.due_day_bs}" if ctype.due_day_bs else ""),
            due_date_ad=due_date_ad,
            assigned_to=req.assigned_staff or req.client.assigned_manager,
            reviewer=req.reviewer,
            priority=ctype.default_priority,
            status=ComplianceDeadline.Status.UPCOMING,
            notes=ctype.penalty_guidelines,
            is_recurring=ctype.frequency != ComplianceType.Frequency.NONE,
            recurrence_frequency=ctype.frequency,
        )

        ComplianceActivity.objects.create(
            firm=firm,
            deadline=deadline,
            action='SCHEDULE_GENERATED',
            from_status='',
            to_status=ComplianceDeadline.Status.UPCOMING,
            description=f"Generated from client requirement profile for {ctype.name}.",
            performed_by=user,
        )
        created_deadlines.append(deadline)

    return created_deadlines
