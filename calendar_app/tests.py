import datetime
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from calendar_app.models import CalendarEvent
from clients.models import Client
from compliance.models import ComplianceDeadline
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus


class CalendarAppIntegrationTests(TestCase):
    def setUp(self):
        self.firm1 = Firm.objects.create(name="Apex Chartered Accountants", slug="apex-ca")
        self.user1 = User.objects.create_user(email="ca.apex@apexca.com.np", password="Password123!")
        FirmMembership.objects.create(firm=self.firm1, user=self.user1, role=FirmRole.CA, status=MembershipStatus.ACTIVE)

        self.firm2 = Firm.objects.create(name="Other CA Firm", slug="other-ca")
        self.user2 = User.objects.create_user(email="ca.other@otherca.com.np", password="Password123!")
        FirmMembership.objects.create(firm=self.firm2, user=self.user2, role=FirmRole.CA, status=MembershipStatus.ACTIVE)

        self.client1 = Client.objects.create(firm=self.firm1, name="Apex Client Pvt Ltd")

    def test_calendar_view_displays_deadlines_and_events(self):
        today = timezone.localdate()
        ComplianceDeadline.objects.create(
            firm=self.firm1,
            title="Annex 5 VAT Return",
            client=self.client1,
            due_date_bs="2081-06-25",
            due_date_ad=today,
            status=ComplianceDeadline.Status.UPCOMING,
        )

        CalendarEvent.objects.create(
            firm=self.firm1,
            title="Field Audit Inspection",
            client=self.client1,
            event_type=CalendarEvent.EventType.AUDIT_VISIT,
            start_time=timezone.now(),
            end_time=timezone.now() + datetime.timedelta(hours=2),
            created_by=self.user1,
        )

        # Other firm deadline (should be isolated)
        ComplianceDeadline.objects.create(
            firm=self.firm2,
            title="Rival Secret Deadline",
            due_date_bs="2081-06-25",
            due_date_ad=today,
            status=ComplianceDeadline.Status.UPCOMING,
        )

        http_client = HttpClient()
        http_client.force_login(self.user1)

        response = http_client.get(reverse('calendar_app:calendar_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annex 5 VAT Return")
        self.assertContains(response, "Field Audit Inspection")
        self.assertNotContains(response, "Rival Secret Deadline")
        self.assertEqual(response.context['statutory_deadlines_count'], 1)
        self.assertEqual(response.context['events_count'], 1)
