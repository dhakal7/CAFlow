import datetime
from django.test import TestCase, Client as TestClient
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
from accounts.models import User
from audit.models import AuditLog
from clients.models import Client
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus
from notifications.models import Notification
from tasks.models import (
    Task,
    TaskActivity,
    TaskAttachment,
    TaskChecklistItem,
    TaskComment,
    WorkflowTemplate,
    WorkflowTemplateItem,
)
from tasks.services import (
    apply_template_to_task,
    create_next_recurring_task,
    ensure_firm_workflow_templates,
)


class TaskModuleTestCase(TestCase):
    def setUp(self):
        # 1. Primary Firm & User
        self.firm = Firm.objects.create(
            name="Dhakal & Associates, CAs",
            slug="dhakal",
            pan_number="102938475",
        )
        self.user = User.objects.create_user(
            email="ca@dhakal.com.np",
            password="testpassword123",
            first_name="Suyog",
            last_name="Dhakal",
        )
        self.membership = FirmMembership.objects.create(
            firm=self.firm,
            user=self.user,
            role=FirmRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        # 2. Staff Member
        self.staff_user = User.objects.create_user(
            email="staff@dhakal.com.np",
            password="testpassword123",
            first_name="Bikash",
            last_name="Karki",
        )
        self.staff_membership = FirmMembership.objects.create(
            firm=self.firm,
            user=self.staff_user,
            role=FirmRole.SENIOR,
            status=MembershipStatus.ACTIVE,
        )

        # 3. Client Entity
        self.client_entity = Client.objects.create(
            firm=self.firm,
            name="Ramesh Sharma",
            business_name="Himalayan Traders Pvt Ltd",
            pan_number="302918273",
        )

        # 4. Another Firm (for tenant isolation tests)
        self.other_firm = Firm.objects.create(
            name="Other Firm & Co",
            slug="other",
            pan_number="998877665",
        )
        self.other_user = User.objects.create_user(
            email="other@firm.com.np",
            password="testpassword123",
        )
        self.other_membership = FirmMembership.objects.create(
            firm=self.other_firm,
            user=self.other_user,
            role=FirmRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        # Ensure templates
        ensure_firm_workflow_templates(self.firm, user=self.user)

        # HTTP Test Client
        self.client = TestClient()
        self.client.login(email="ca@dhakal.com.np", password="testpassword123")
        session = self.client.session
        session['active_firm_id'] = str(self.firm.id)
        session.save()

    def test_task_list_board_view(self):
        """Verify Task Board renders columns: Pending, In Progress, Review, Completed."""
        task1 = Task.objects.create(
            firm=self.firm,
            title="Monthly VAT Filing",
            client=self.client_entity,
            assigned_to=self.staff_user,
            status=Task.Status.TODO,
            priority=Task.Priority.HIGH,
            due_date=timezone.localdate() + datetime.timedelta(days=2),
        )
        task2 = Task.objects.create(
            firm=self.firm,
            title="TDS Scrutiny",
            client=self.client_entity,
            assigned_to=self.user,
            status=Task.Status.IN_PROGRESS,
            priority=Task.Priority.URGENT,
            due_date=timezone.localdate(),
        )

        response = self.client.get('/tasks/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tasks")
        self.assertContains(response, "Manage your firm's work and deadlines.")
        self.assertContains(response, "Pending")
        self.assertContains(response, "In Progress")
        self.assertContains(response, "Review")
        self.assertContains(response, "Completed")
        self.assertContains(response, "Monthly VAT Filing")
        self.assertContains(response, "TDS Scrutiny")

    def test_task_list_table_view(self):
        """Verify List view renders tabular tasks and pagination."""
        Task.objects.create(
            firm=self.firm,
            title="OCR Form 21 Submission",
            client=self.client_entity,
            status=Task.Status.TODO,
            priority=Task.Priority.MEDIUM,
        )
        response = self.client.get('/tasks/?view=list')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OCR Form 21 Submission")
        self.assertContains(response, "Himalayan Traders Pvt Ltd")

    def test_task_list_calendar_view(self):
        """Verify Calendar view renders deadline groups."""
        today = timezone.localdate()
        Task.objects.create(
            firm=self.firm,
            title="Statutory Trial Balance Audit",
            client=self.client_entity,
            status=Task.Status.IN_PROGRESS,
            due_date=today,
        )
        response = self.client.get('/tasks/?view=calendar')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming Deadlines Calendar")
        self.assertContains(response, today.isoformat())

    def test_create_task_with_workflow_template(self):
        """Verify creating a task with a workflow template generates standard checklist steps."""
        vat_template = WorkflowTemplate.objects.filter(firm=self.firm, title='Monthly VAT Workflow').first()
        self.assertIsNotNone(vat_template)

        post_data = {
            'title': 'Bhadra 2081 VAT Return',
            'description': 'Monthly VAT filing procedure for Himalayan Traders',
            'client': str(self.client_entity.id),
            'service': 'TAX_VAT',
            'assigned_to': str(self.staff_user.id),
            'priority': Task.Priority.HIGH,
            'status': Task.Status.TODO,
            'due_date': (timezone.localdate() + datetime.timedelta(days=5)).isoformat(),
            'template_id': str(vat_template.id),
            'is_recurring': 'on',
            'recurrence_interval': Task.RecurrenceInterval.MONTHLY,
        }

        response = self.client.post('/tasks/create/', post_data)
        self.assertEqual(response.status_code, 302)

        task = Task.objects.filter(firm=self.firm, title='Bhadra 2081 VAT Return').first()
        self.assertIsNotNone(task)
        self.assertEqual(task.client, self.client_entity)
        self.assertEqual(task.assigned_to, self.staff_user)
        self.assertTrue(task.is_recurring)
        self.assertEqual(task.recurrence_interval, Task.RecurrenceInterval.MONTHLY)

        # Check template checklist was applied
        checklist_count = task.checklist_items.count()
        self.assertEqual(checklist_count, 8)
        self.assertTrue(task.checklist_items.filter(title='Request documents').exists())
        self.assertTrue(task.checklist_items.filter(title='CA review').exists())

        # Check activity was recorded
        self.assertTrue(task.activities.filter(action_type=TaskActivity.ActionType.CREATED).exists())

    def test_task_detail_view(self):
        """Verify Task Detail shows Title, Client, Assignee, Priority, Checklist, Comments, Activity."""
        task = Task.objects.create(
            firm=self.firm,
            title="Trial Balance Audit Verification",
            description="Verify opening ledgers and bank balances.",
            client=self.client_entity,
            assigned_to=self.staff_user,
            status=Task.Status.IN_PROGRESS,
            priority=Task.Priority.URGENT,
            due_date=timezone.localdate(),
        )
        TaskChecklistItem.objects.create(firm=self.firm, task=task, title="Scrutinize ledger vouchers")
        TaskComment.objects.create(firm=self.firm, task=task, user=self.user, content="Bank confirmation letter dispatched.")
        TaskActivity.objects.create(firm=self.firm, task=task, action_type=TaskActivity.ActionType.CREATED, description="Initial task created")

        response = self.client.get(f'/tasks/{task.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trial Balance Audit Verification")
        self.assertContains(response, "Himalayan Traders Pvt Ltd")
        self.assertContains(response, "Bikash Karki")
        self.assertContains(response, "Scrutinize ledger vouchers")
        self.assertContains(response, "Bank confirmation letter dispatched.")
        self.assertContains(response, "Initial task created")

    def test_status_change_and_recurring_task_generation(self):
        """Verify advancing task status to COMPLETED triggers recurring task creation."""
        due = timezone.localdate()
        task = Task.objects.create(
            firm=self.firm,
            title="Monthly TDS Return",
            client=self.client_entity,
            assigned_to=self.staff_user,
            status=Task.Status.UNDER_REVIEW,
            priority=Task.Priority.HIGH,
            due_date=due,
            is_recurring=True,
            recurrence_interval=Task.RecurrenceInterval.MONTHLY,
        )
        TaskChecklistItem.objects.create(firm=self.firm, task=task, title="Verify TDS receipts")

        response = self.client.post(f'/tasks/{task.id}/status/', {'status': 'COMPLETED'})
        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(task.completed_at)

        # Check that the next month's recurring task was automatically spawned
        spawned = Task.objects.filter(firm=self.firm, title="Monthly TDS Return", status=Task.Status.TODO).first()
        self.assertIsNotNone(spawned)
        self.assertGreater(spawned.due_date, task.due_date)
        self.assertTrue(spawned.checklist_items.filter(title="Verify TDS receipts").exists())

    def test_checklist_toggle_ajax(self):
        """Verify toggling checklist item updates completion state and recalculates progress."""
        task = Task.objects.create(
            firm=self.firm,
            title="Fixed Asset Audit",
            client=self.client_entity,
            status=Task.Status.TODO,
        )
        item1 = TaskChecklistItem.objects.create(firm=self.firm, task=task, title="Physical verification", order=1)
        item2 = TaskChecklistItem.objects.create(firm=self.firm, task=task, title="Depreciation schedule", order=2)

        response = self.client.post(
            f'/tasks/checklist/{item1.id}/toggle/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_completed'])
        self.assertEqual(data['stats']['completed'], 1)
        self.assertEqual(data['stats']['total'], 2)
        self.assertEqual(data['stats']['percent'], 50)

    def test_comment_and_assignment_actions(self):
        """Verify adding comment and changing staff assignment."""
        task = Task.objects.create(firm=self.firm, title="Income Tax Computation")

        # Comment
        resp_comment = self.client.post(f'/tasks/{task.id}/comment/', {'content': 'Section 12 deduction checked.'})
        self.assertEqual(resp_comment.status_code, 302)
        self.assertEqual(task.comments.count(), 1)
        self.assertEqual(task.comments.first().content, 'Section 12 deduction checked.')

        # Assign
        resp_assign = self.client.post(f'/tasks/{task.id}/assign/', {'assigned_to': str(self.staff_user.id)})
        self.assertEqual(resp_assign.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.assigned_to, self.staff_user)

    def test_workflow_template_creation(self):
        """Verify creating custom workflow template."""
        post_data = {
            'title': 'Internal Audit Risk Assessment',
            'service': 'INTERNAL_AUDIT',
            'default_priority': 'HIGH',
            'estimated_days': 14,
            'description': 'Standard operating steps for internal audit',
            'checklist_lines': 'Review internal control policy\nInterview department leads\nSample test expense vouchers\nIssue draft report',
        }
        response = self.client.post('/tasks/templates/create/', post_data)
        self.assertEqual(response.status_code, 302)

        tpl = WorkflowTemplate.objects.filter(firm=self.firm, title='Internal Audit Risk Assessment').first()
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl.items.count(), 4)

    def test_tenant_isolation(self):
        """Ensure users cannot view or manipulate tasks from another firm."""
        other_task = Task.objects.create(
            firm=self.other_firm,
            title="Confidential Audit of Firm 2",
        )

        # Attempt to access from firm 1 user
        response = self.client.get(f'/tasks/{other_task.id}/')
        self.assertEqual(response.status_code, 404)

        # Attempt to modify status
        response_status = self.client.post(f'/tasks/{other_task.id}/status/', {'status': 'COMPLETED'})
        self.assertEqual(response_status.status_code, 404)

    def test_task_crud_with_extended_fields(self):
        """Verify task creation with start_date, estimated_hours, category, and deletion."""
        today = timezone.localdate()
        post_data = {
            'title': 'Corporate Tax Assessment FY 2081/82',
            'description': 'Tax assessment review with IRD officer',
            'client': str(self.client_entity.id),
            'service': 'TAX_VAT',
            'category': 'Corporate Tax',
            'assigned_to': str(self.staff_user.id),
            'priority': Task.Priority.URGENT,
            'start_date': today.isoformat(),
            'due_date': (today + datetime.timedelta(days=10)).isoformat(),
            'estimated_hours': '12.50',
            'status': Task.Status.TODO,
        }

        response = self.client.post('/tasks/create/', post_data)
        self.assertEqual(response.status_code, 302)

        task = Task.objects.filter(firm=self.firm, title='Corporate Tax Assessment FY 2081/82').first()
        self.assertIsNotNone(task)
        self.assertEqual(task.category, 'Corporate Tax')
        self.assertEqual(task.start_date, today)
        self.assertEqual(task.estimated_hours, Decimal('12.50'))

        # Edit task
        edit_data = post_data.copy()
        edit_data['estimated_hours'] = '15.00'
        edit_data['priority'] = Task.Priority.HIGH
        resp_edit = self.client.post(f'/tasks/{task.id}/edit/', edit_data)
        self.assertEqual(resp_edit.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.estimated_hours, Decimal('15.00'))
        self.assertEqual(task.priority, Task.Priority.HIGH)

        # Delete task
        resp_delete = self.client.post(f'/tasks/{task.id}/delete/')
        self.assertEqual(resp_delete.status_code, 302)
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_cross_firm_protection_model_and_view(self):
        """Verify cross-firm protection: attaching another firm's client raises ValidationError / rejected."""
        other_client = Client.objects.create(
            firm=self.other_firm,
            name="Firm 2 Client Corp",
            pan_number="888111222",
        )

        # 1. Model level protection
        cross_task = Task(
            firm=self.firm,
            title="Illegal Cross-Firm Task",
            client=other_client,
        )
        with self.assertRaises(ValidationError):
            cross_task.clean()

        with self.assertRaises(ValueError):
            cross_task.save()

        # 2. View/form level protection
        post_data = {
            'title': 'Cross firm hack',
            'client': str(other_client.id),
            'priority': Task.Priority.LOW,
            'status': Task.Status.TODO,
        }
        resp = self.client.post('/tasks/create/', post_data)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Task.objects.filter(firm=self.firm, title='Cross firm hack').exists())

    def test_recurring_behavior_idempotence_no_duplicates(self):
        """Verify that recurring task spawning is idempotent and does not create duplicate tasks."""
        today = timezone.localdate()
        task = Task.objects.create(
            firm=self.firm,
            title="Monthly Annex-13 Reconciliation",
            client=self.client_entity,
            assigned_to=self.staff_user,
            due_date=today,
            is_recurring=True,
            recurrence_interval=Task.RecurrenceInterval.MONTHLY,
            category="VAT Audit",
            estimated_hours=Decimal('6.00'),
        )

        # First trigger
        next1 = create_next_recurring_task(task, user=self.user)
        self.assertIsNotNone(next1)
        self.assertEqual(next1.category, "VAT Audit")
        self.assertEqual(next1.estimated_hours, Decimal('6.00'))

        # Second trigger (should return existing next task without creating a duplicate)
        next2 = create_next_recurring_task(task, user=self.user)
        self.assertEqual(next1.id, next2.id)

        matching_count = Task.objects.filter(
            firm=self.firm,
            client=self.client_entity,
            title="Monthly Annex-13 Reconciliation",
            due_date=next1.due_date,
        ).count()
        self.assertEqual(matching_count, 1)

    def test_workflow_generation_no_checklist_duplicates(self):
        """Verify that when a template is selected and checklist steps are submitted, items are not duplicated."""
        vat_template = WorkflowTemplate.objects.filter(firm=self.firm, title='Monthly VAT Workflow').first()
        self.assertIsNotNone(vat_template)
        template_item_count = vat_template.items.count()

        # Simulate modal submit where JS pre-filled the steps
        submitted_steps = [item.title for item in vat_template.items.all()]

        post_data = {
            'title': 'Ashwin VAT Filing Engagement',
            'client': str(self.client_entity.id),
            'template_id': str(vat_template.id),
            'checklist_raw': str(submitted_steps).replace("'", '"'),
            'priority': Task.Priority.HIGH,
            'status': Task.Status.TODO,
        }

        resp = self.client.post('/tasks/create/', post_data)
        self.assertEqual(resp.status_code, 302)

        task = Task.objects.filter(firm=self.firm, title='Ashwin VAT Filing Engagement').first()
        self.assertIsNotNone(task)
        # Checklist items count must equal exactly the submitted steps, NOT double
        self.assertEqual(task.checklist_items.count(), template_item_count)

    def test_overdue_calculations(self):
        """Verify is_overdue flag and days_remaining calculations."""
        today = timezone.localdate()
        past_task = Task.objects.create(
            firm=self.firm,
            title="Overdue Tax Return",
            due_date=today - datetime.timedelta(days=3),
            status=Task.Status.TODO,
        )
        self.assertTrue(past_task.is_overdue)
        self.assertEqual(past_task.days_remaining, -3)

        # When completed, is_overdue must be False
        past_task.status = Task.Status.COMPLETED
        past_task.save()
        self.assertFalse(past_task.is_overdue)

        # Future task
        future_task = Task.objects.create(
            firm=self.firm,
            title="Future Filing",
            due_date=today + datetime.timedelta(days=5),
            status=Task.Status.TODO,
        )
        self.assertFalse(future_task.is_overdue)
        self.assertEqual(future_task.days_remaining, 5)

    def test_all_workflow_statuses(self):
        """Verify all 6 workflow statuses: To Do, In Progress, Waiting, Review, Completed, Cancelled."""
        task = Task.objects.create(
            firm=self.firm,
            title="Status Lifecycle Task",
            status=Task.Status.TODO,
        )
        self.assertEqual(task.get_status_display(), "To Do")

        stages = [
            (Task.Status.IN_PROGRESS, "In Progress"),
            (Task.Status.BLOCKED, "Waiting"),
            (Task.Status.UNDER_REVIEW, "Review"),
            (Task.Status.COMPLETED, "Completed"),
            (Task.Status.CANCELLED, "Cancelled"),
        ]
        for status_code, expected_display in stages:
            resp = self.client.post(f'/tasks/{task.id}/status/', {'status': status_code})
            self.assertEqual(resp.status_code, 302)
            task.refresh_from_db()
            self.assertEqual(task.status, status_code)
            self.assertEqual(task.get_status_display(), expected_display)

    def test_notifications_generated_on_assignment_and_comments(self):
        """Verify that task assignments and comments generate notifications for users."""
        # 1. Assignment notification
        task = Task.objects.create(
            firm=self.firm,
            title="Audit Scrutiny Note",
            created_by=self.user,
        )
        # Assign to staff_user
        self.client.post(f'/tasks/{task.id}/assign/', {'assigned_to': str(self.staff_user.id)})
        notif = Notification.objects.filter(recipient=self.staff_user, notification_type=Notification.NotificationType.TASK).first()
        self.assertIsNotNone(notif)
        self.assertIn("Task Assigned", notif.title)
        self.assertIn("Audit Scrutiny Note", notif.title)

        # 2. Comment notification
        task.refresh_from_db()
        self.client.post(f'/tasks/{task.id}/comment/', {'content': 'Please verify bank balance by Friday.'})
        comment_notif = Notification.objects.filter(
            recipient=self.staff_user,
            title__contains="New comment on 'Audit Scrutiny Note'",
        ).first()
        self.assertIsNotNone(comment_notif)
        self.assertIn("bank balance", comment_notif.message)

    def test_activity_history_and_audit_logging(self):
        """Verify that task operations record TaskActivity and firm AuditLog."""
        task = Task.objects.create(
            firm=self.firm,
            title="Statutory Audit Working Paper",
            created_by=self.user,
        )
        # Add comment
        self.client.post(f'/tasks/{task.id}/comment/', {'content': 'Review complete.'})

        # Check TaskActivity
        self.assertTrue(task.activities.filter(action_type=TaskActivity.ActionType.COMMENT_ADDED).exists())

        # Check AuditLog
        self.assertTrue(AuditLog.objects.filter(firm=self.firm, object_type='Task', object_id=str(task.id)).exists())
