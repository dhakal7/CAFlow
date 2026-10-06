import random
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.services import get_default_demo_firm
from clients.models import Client
from clients.constants import SERVICE_CHOICES
from tasks.models import (
    Task,
    TaskChecklistItem,
    TaskComment,
    TaskActivity,
    WorkflowTemplate,
)
from tasks.services import ensure_firm_workflow_templates


class Command(BaseCommand):
    help = "Seeds default CA workflow templates and enriches existing tasks with checklist items, comments, and activities"

    def handle(self, *args, **options):
        self.stdout.write("Seeding workflow templates & rich task details...")
        firm = get_default_demo_firm()
        if not firm:
            self.stdout.write(self.style.ERROR("No demo firm found."))
            return

        # 1. Ensure Workflow Templates
        templates = ensure_firm_workflow_templates(firm)
        self.stdout.write(f"Ensured {WorkflowTemplate.objects.filter(firm=firm).count()} workflow templates.")

        # 2. Enrich tasks with services, checklists, and activity
        tasks = Task.objects.filter(firm=firm)
        sample_checklist_bank = [
            "Verify opening trial balance with prior year audited report",
            "Scrutinize sales register against VAT returns submitted to IRD",
            "Audit TDS deductions under Section 87/88 against ETDS portal",
            "Obtain direct bank confirmation letters for all active accounts",
            "Inspect physical stock verification count sheets and valuation",
            "Review OCR Form 21, shareholder ledger & board minute book",
            "Prepare working paper lead schedules for Trade Payables",
            "Review legal expenses and contingent tax appeal notices",
            "Senior Associate review & clearance of audit queries",
            "Partner sign-off and issue independent audit opinion",
        ]

        sample_comments = [
            "Requested purchase register for Bhadra from client accountant; waiting on reconciliation.",
            "TDS under Sec 88 discrepancy identified in contract payments. Reconciled with voucher #402.",
            "Working paper updated with IRD portal acknowledgement receipt.",
            "Partner reviewed opening balance scrutiny; clearance given to proceed to final reporting.",
        ]

        services_keys = [s[0] for s in SERVICE_CHOICES]

        for i, task in enumerate(tasks):
            # Assign service if not set
            if not task.service:
                task.service = services_keys[i % len(services_keys)]
                task.save(update_fields=['service'])

            # Add checklist items if none exist
            if task.checklist_items.count() == 0:
                num_items = random.randint(3, 6)
                chosen_items = random.sample(sample_checklist_bank, num_items)
                
                # If completed task, all are completed; otherwise partial
                is_task_done = (task.status == Task.Status.COMPLETED)
                num_completed = num_items if is_task_done else random.randint(0, num_items - 1)
                
                for idx, title in enumerate(chosen_items, start=1):
                    item_completed = (idx <= num_completed)
                    TaskChecklistItem.objects.create(
                        firm=firm,
                        task=task,
                        title=title,
                        is_completed=item_completed,
                        completed_at=timezone.now() if item_completed else None,
                        order=idx,
                    )

            # Add activity if none
            if task.activities.count() == 0:
                TaskActivity.objects.create(
                    firm=firm,
                    task=task,
                    action_type=TaskActivity.ActionType.CREATED,
                    description=f"Task '{task.title}' created and assigned to {task.assigned_to or 'General Pool'}",
                    user=task.assigned_to,
                )
                if task.status in [Task.Status.IN_PROGRESS, Task.Status.UNDER_REVIEW, Task.Status.COMPLETED]:
                    TaskActivity.objects.create(
                        firm=firm,
                        task=task,
                        action_type=TaskActivity.ActionType.STATUS_CHANGED,
                        description=f"Status advanced to {task.get_status_display()}",
                        user=task.assigned_to,
                    )

            # Add a comment if none
            if task.comments.count() == 0 and i % 2 == 0:
                TaskComment.objects.create(
                    firm=firm,
                    task=task,
                    user=task.assigned_to or firm.memberships.first().user,
                    content=sample_comments[i % len(sample_comments)],
                )

        self.stdout.write(self.style.SUCCESS("Successfully seeded templates and task workflow data!"))
