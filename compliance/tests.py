import datetime
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import CalendarEvent
from clients.models import Client
from documents.models import Document
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus
from notifications.models import Notification
from tasks.models import Task
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


class BaseComplianceTestCase(TestCase):
    """Setup multi-firm testing environment."""
    def setUp(self):
        # 1. Firm 1 (Primary)
        self.firm1 = Firm.objects.create(
            name="Dhakal & Associates CA",
            slug="dhakal-ca",
            current_fiscal_year="2081/82",
        )
        self.user1 = User.objects.create_user(
            email="ca.suyog@dhakal.com.np",
            password="Password123!",
            first_name="Suyog",
            last_name="Dhakal",
        )
        self.membership1 = FirmMembership.objects.create(
            firm=self.firm1,
            user=self.user1,
            role=FirmRole.CA,
            status=MembershipStatus.ACTIVE,
        )

        self.staff1 = User.objects.create_user(
            email="staff.bikash@dhakal.com.np",
            password="Password123!",
            first_name="Bikash",
            last_name="Karki",
        )
        self.membership_staff = FirmMembership.objects.create(
            firm=self.firm1,
            user=self.staff1,
            role=FirmRole.STAFF,
            status=MembershipStatus.ACTIVE,
        )

        self.client1 = Client.objects.create(
            firm=self.firm1,
            name="Himalayan Traders Pvt Ltd",
            business_name="Himalayan Traders Pvt Ltd",
            pan_number="601928374",
        )

        # 2. Firm 2 (Secondary for tenant isolation tests)
        self.firm2 = Firm.objects.create(
            name="Rival Accounting Firm",
            slug="rival-ca",
            current_fiscal_year="2081/82",
        )
        self.user2 = User.objects.create_user(
            email="other@rivalca.com.np",
            password="Password123!",
            first_name="Other",
            last_name="Auditor",
        )
        self.membership2 = FirmMembership.objects.create(
            firm=self.firm2,
            user=self.user2,
            role=FirmRole.CA,
            status=MembershipStatus.ACTIVE,
        )
        self.client2 = Client.objects.create(
            firm=self.firm2,
            name="Rival Client Ent",
            business_name="Rival Client Ent",
            pan_number="300998877",
        )


class ComplianceCRUDAndValidationTests(BaseComplianceTestCase):
    """Tests create, edit, delete, and cross-firm validation on ComplianceDeadline."""

    def test_create_compliance_deadline(self):
        today = timezone.localdate()
        ctype = ComplianceType.objects.create(
            firm=self.firm1,
            name="Monthly VAT Return",
            category=ComplianceType.Category.VAT,
            frequency=ComplianceType.Frequency.MONTHLY,
        )

        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Monthly VAT Filing - Bhadra 2081",
            client=self.client1,
            compliance_type=ctype,
            governing_act=ComplianceDeadline.GoverningAct.VAT,
            period="Bhadra 2081",
            due_date_bs="2081-06-25",
            due_date_ad=today + datetime.timedelta(days=5),
            assigned_to=self.staff1,
            reviewer=self.user1,
            priority=ComplianceDeadline.Priority.URGENT,
            status=ComplianceDeadline.Status.UPCOMING,
            notes="Annex 5 and 6 verification required.",
        )
        self.assertIsNotNone(deadline.id)
        self.assertEqual(deadline.period, "Bhadra 2081")
        self.assertEqual(deadline.assigned_to, self.staff1)
        self.assertEqual(deadline.reviewer, self.user1)
        self.assertFalse(deadline.is_overdue)

    def test_edit_compliance_deadline(self):
        today = timezone.localdate()
        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Initial Title",
            client=self.client1,
            due_date_bs="2081-06-25",
            due_date_ad=today,
            status=ComplianceDeadline.Status.UPCOMING,
        )

        deadline.title = "Updated VAT Title"
        deadline.notes = "Updated notes"
        deadline.filing_reference_number = "TOKEN-2081-123"
        deadline.save()

        deadline.refresh_from_db()
        self.assertEqual(deadline.title, "Updated VAT Title")
        self.assertEqual(deadline.filing_reference_number, "TOKEN-2081-123")

    def test_delete_compliance_deadline(self):
        today = timezone.localdate()
        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="To be deleted",
            client=self.client1,
            due_date_bs="2081-06-25",
            due_date_ad=today,
        )
        deadline_id = deadline.id
        deadline.delete()
        self.assertFalse(ComplianceDeadline.objects.filter(id=deadline_id).exists())

    def test_firm_isolation_validation_rejects_foreign_client(self):
        """Cannot assign a client from Firm 2 to a deadline in Firm 1."""
        today = timezone.localdate()
        with self.assertRaises((ValueError, Exception)):
            ComplianceDeadline.objects.create(
                firm=self.firm1,
                title="Cross firm attack",
                client=self.client2,  # belongs to firm2!
                due_date_bs="2081-06-25",
                due_date_ad=today,
            )


class ConfigurableComplianceTypeTests(BaseComplianceTestCase):
    """Tests configurable types and client compliance subscriptions."""

    def test_ensure_default_compliance_types(self):
        types = ensure_default_compliance_types(self.firm1)
        self.assertGreater(len(types), 0)
        self.assertTrue(ComplianceType.objects.filter(firm=self.firm1, code='VAT_MONTHLY').exists())
        self.assertTrue(ComplianceType.objects.filter(firm=self.firm1, code='TDS_MONTHLY').exists())
        self.assertTrue(ComplianceType.objects.filter(firm=self.firm1, code='INCOME_TAX_ADVANCE').exists())

    def test_client_compliance_requirement_subscription(self):
        ctype = ComplianceType.objects.create(
            firm=self.firm1,
            name="Quarterly TDS Withholding",
            category=ComplianceType.Category.TDS,
            frequency=ComplianceType.Frequency.QUARTERLY,
        )

        req = ClientComplianceRequirement.objects.create(
            firm=self.firm1,
            client=self.client1,
            compliance_type=ctype,
            frequency=ComplianceType.Frequency.QUARTERLY,
            assigned_staff=self.staff1,
            reviewer=self.user1,
            notes="Client uses IRD e-portal bi-monthly",
        )
        self.assertIsNotNone(req.id)
        self.assertEqual(req.client, self.client1)
        self.assertEqual(req.compliance_type, ctype)

    def test_schedule_generator_from_requirements(self):
        ctype = ComplianceType.objects.create(
            firm=self.firm1,
            name="Monthly SSF Deposit",
            category=ComplianceType.Category.LABOUR_ACT,
            frequency=ComplianceType.Frequency.MONTHLY,
            due_day_bs=30,
        )
        ClientComplianceRequirement.objects.create(
            firm=self.firm1,
            client=self.client1,
            compliance_type=ctype,
            assigned_staff=self.staff1,
        )

        today = timezone.localdate()
        created = generate_deadlines_from_client_requirements(
            firm=self.firm1,
            target_period_name="Ashoj 2081",
            due_date_bs="2081-06-30",
            due_date_ad=today + datetime.timedelta(days=7),
            user=self.user1,
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].client, self.client1)
        self.assertEqual(created[0].period, "Ashoj 2081")


class ComplianceWorkflowAndTransitionsTests(BaseComplianceTestCase):
    """Tests the full compliance workflow: Deadline -> Preparation -> Documents -> Review -> Filing -> Completed."""

    def test_workflow_transitions_and_notifications(self):
        today = timezone.localdate()
        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="VAT Return Bhadra 2081",
            client=self.client1,
            due_date_bs="2081-06-25",
            due_date_ad=today + datetime.timedelta(days=4),
            assigned_to=self.staff1,
            reviewer=self.user1,
            status=ComplianceDeadline.Status.UPCOMING,
            is_recurring=True,
            recurrence_frequency=ComplianceDeadline.RecurrenceFrequency.MONTHLY,
        )

        # 1. Preparation stage
        transition_compliance_status(deadline, ComplianceDeadline.Status.IN_PROGRESS, user=self.staff1)
        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.IN_PROGRESS)

        # 2. Waiting for client
        transition_compliance_status(deadline, ComplianceDeadline.Status.WAITING_FOR_CLIENT, user=self.staff1, notes="Waiting for purchase book")
        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.WAITING_FOR_CLIENT)

        # 3. Ready for Review (notifies reviewer)
        transition_compliance_status(deadline, ComplianceDeadline.Status.READY_FOR_REVIEW, user=self.staff1)
        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.READY_FOR_REVIEW)
        # Check reviewer received notification
        self.assertTrue(Notification.objects.filter(recipient=self.user1, notification_type=Notification.NotificationType.COMPLIANCE).exists())

        # 4. Filed stage
        transition_compliance_status(deadline, ComplianceDeadline.Status.FILED, user=self.user1, filing_reference_number="IRD-VAT-99881")
        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.FILED)
        self.assertEqual(deadline.filing_reference_number, "IRD-VAT-99881")

        # 5. Completed stage (triggers next recurring deadline)
        transition_compliance_status(deadline, ComplianceDeadline.Status.COMPLETED, user=self.user1)
        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.COMPLETED)
        self.assertIsNotNone(deadline.completion_date)

        # Check recurring successor deadline was generated
        successors = ComplianceDeadline.objects.filter(
            firm=self.firm1,
            client=self.client1,
            status=ComplianceDeadline.Status.UPCOMING,
        )
        self.assertEqual(successors.count(), 1)
        self.assertGreater(successors.first().due_date_ad, deadline.due_date_ad)

    def test_linking_tasks_and_documents(self):
        today = timezone.localdate()
        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Statutory Audit Working Papers",
            client=self.client1,
            due_date_bs="2081-09-30",
            due_date_ad=today + datetime.timedelta(days=30),
        )

        task = Task.objects.create(
            firm=self.firm1,
            title="Verify Inventory Valuation NAS 2",
            client=self.client1,
        )
        deadline.tasks.add(task)
        self.assertIn(task, deadline.tasks.all())

        doc = Document.objects.create(
            firm=self.firm1,
            client=self.client1,
            title="Trial Balance Signed Copy",
            category=Document.Category.AUDIT_WORKING_PAPERS,
        )
        deadline.documents.add(doc)
        self.assertIn(doc, deadline.documents.all())


class OverdueLogicTests(BaseComplianceTestCase):
    """Tests automatic identification and notifications for overdue compliance items."""

    def test_auto_identify_overdue_deadlines(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Overdue SSF Payment",
            client=self.client1,
            due_date_bs="2081-06-20",
            due_date_ad=yesterday,
            assigned_to=self.staff1,
            reviewer=self.user1,
            status=ComplianceDeadline.Status.UPCOMING,
        )
        self.assertTrue(deadline.is_overdue)

        # Run auto-scan service
        count = check_and_update_overdue_deadlines(firm=self.firm1)
        self.assertEqual(count, 1)

        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.OVERDUE)

        # Assigned staff should have received OVERDUE notification
        overdue_notif = Notification.objects.filter(
            recipient=self.staff1,
            title__icontains="OVERDUE",
        )
        self.assertTrue(overdue_notif.exists())

    def test_completed_deadlines_not_flagged_overdue(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        deadline = ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Completed Past Filing",
            client=self.client1,
            due_date_bs="2081-06-20",
            due_date_ad=yesterday,
            status=ComplianceDeadline.Status.COMPLETED,
        )
        self.assertFalse(deadline.is_overdue)
        count = check_and_update_overdue_deadlines(firm=self.firm1)
        self.assertEqual(count, 0)
        deadline.refresh_from_db()
        self.assertEqual(deadline.status, ComplianceDeadline.Status.COMPLETED)


class CalendarIntegrationTests(BaseComplianceTestCase):
    """Tests compliance deadlines appear in the calendar view alongside calendar events."""

    def test_calendar_view_displays_compliance_deadlines(self):
        today = timezone.localdate()
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Monthly VAT Filing",
            client=self.client1,
            due_date_bs="2081-06-25",
            due_date_ad=today + datetime.timedelta(days=2),
            status=ComplianceDeadline.Status.UPCOMING,
        )

        CalendarEvent.objects.create(
            firm=self.firm1,
            title="Dam Site Physical Inspection",
            client=self.client1,
            event_type=CalendarEvent.EventType.AUDIT_VISIT,
            start_time=timezone.now() + datetime.timedelta(days=3),
            end_time=timezone.now() + datetime.timedelta(days=3, hours=2),
            created_by=self.user1,
        )

        http_client = HttpClient()
        http_client.force_login(self.user1)

        response = http_client.get(reverse('calendar_app:calendar_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monthly VAT Filing")
        self.assertContains(response, "Dam Site Physical Inspection")
        self.assertEqual(response.context['statutory_deadlines_count'], 1)
        self.assertEqual(response.context['events_count'], 1)


class FirmIsolationAndPermissionsTests(BaseComplianceTestCase):
    """Tests multi-firm tenant boundary enforcement and RBAC."""

    def test_firm_isolation_in_compliance_list(self):
        today = timezone.localdate()
        # Firm 1 item
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Firm 1 Secret Filing",
            client=self.client1,
            due_date_bs="2081-06-25",
            due_date_ad=today,
        )
        # Firm 2 item
        ComplianceDeadline.objects.create(
            firm=self.firm2,
            title="Firm 2 Private Audit",
            client=self.client2,
            due_date_bs="2081-06-25",
            due_date_ad=today,
        )

        http_client = HttpClient()
        http_client.force_login(self.user1)  # Firm 1 user

        response = http_client.get(reverse('compliance:compliance_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Firm 1 Secret Filing")
        self.assertNotContains(response, "Firm 2 Private Audit")

    def test_permission_denial_for_manage_compliance(self):
        """Staff without manage_compliance cannot create a deadline."""
        http_client = HttpClient()
        http_client.force_login(self.staff1)  # Role STAFF: has view_compliance but not manage_compliance

        today = timezone.localdate()
        response = http_client.post(reverse('compliance:compliance_create'), {
            'title': 'Unauthorized Deadline',
            'client': str(self.client1.id),
            'due_date_bs': '2081-06-25',
            'due_date_ad': today.strftime('%Y-%m-%d'),
        })
        self.assertEqual(response.status_code, 403)


class DashboardMetricsTests(BaseComplianceTestCase):
    """Tests compliance metrics calculation."""

    def test_dashboard_metrics_counts(self):
        today = timezone.localdate()
        # Due today
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Due Today Filing",
            due_date_bs="2081-06-25",
            due_date_ad=today,
            status=ComplianceDeadline.Status.UPCOMING,
        )
        # Overdue
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Overdue Filing",
            due_date_bs="2081-06-20",
            due_date_ad=today - datetime.timedelta(days=2),
            status=ComplianceDeadline.Status.OVERDUE,
        )
        # Waiting for client
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Waiting Books",
            due_date_bs="2081-07-10",
            due_date_ad=today + datetime.timedelta(days=15),
            status=ComplianceDeadline.Status.WAITING_FOR_CLIENT,
        )
        # Completed
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Completed Filing",
            due_date_bs="2081-06-15",
            due_date_ad=today - datetime.timedelta(days=10),
            status=ComplianceDeadline.Status.COMPLETED,
        )

        metrics = get_compliance_dashboard_metrics(self.firm1)
        self.assertEqual(metrics['due_today'], 1)
        self.assertEqual(metrics['overdue'], 1)
        self.assertEqual(metrics['waiting_for_client'], 1)
        self.assertEqual(metrics['completed'], 1)
