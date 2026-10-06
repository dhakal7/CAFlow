from django.core.exceptions import ValidationError
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from audit.models import AuditLog
from billing.models import Invoice
from calendar_app.models import CalendarEvent
from clients.models import Client, ClientActivity
from compliance.models import ComplianceDeadline
from documents.models import Document, DocumentRequest
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus
from messages_app.models import ChatMessage, Conversation
from tasks.models import Task


class ClientCRMTests(TestCase):
    """
    Comprehensive test suite for CAFlow Client CRM Module.
    Tests tenant isolation, search, filters, multi-step creation, actions, and empty states.
    """
    def setUp(self):
        # 1. Firm A (Dhakal & Associates)
        self.firm_a = Firm.objects.create(name='Dhakal & Associates', slug='dhakal-assoc')
        self.user_a1 = User.objects.create_user('suyog@dhakal.com.np', 'Password123!', first_name='Suyog', last_name='Dhakal')
        self.user_a2 = User.objects.create_user('anjali@dhakal.com.np', 'Password123!', first_name='Anjali', last_name='Sharma')
        FirmMembership.objects.create(user=self.user_a1, firm=self.firm_a, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.user_a2, firm=self.firm_a, role=FirmRole.CA, status=MembershipStatus.ACTIVE)

        # 2. Firm B (Pokhara Tax Partners)
        self.firm_b = Firm.objects.create(name='Pokhara Tax Partners', slug='pokhara-tax')
        self.user_b1 = User.objects.create_user('bikash@pokhara.com.np', 'Password123!', first_name='Bikash', last_name='Karki')
        FirmMembership.objects.create(user=self.user_b1, firm=self.firm_b, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)

        # 3. Create Sample Clients for Firm A
        self.client_a1 = Client.objects.create(
            firm=self.firm_a,
            name='Ramesh Adhikari',
            business_name='Himalayan Traders Pvt Ltd',
            pan_number='601928374',
            client_type=Client.ClientType.PVT_LTD,
            contact_person='Ramesh Adhikari',
            email='ramesh@himalayan.com.np',
            phone='+977-9851000001',
            status=Client.Status.ACTIVE,
            fiscal_year='2081/82',
            services=['STATUTORY_AUDIT', 'TAX_VAT'],
            assigned_manager=self.user_a1,
        )
        self.client_a1.assigned_staff.add(self.user_a2)

        self.client_a2 = Client.objects.create(
            firm=self.firm_a,
            name='Er. Sunil Thapa',
            business_name='Apex Hydropower Ltd',
            pan_number='300481920',
            client_type=Client.ClientType.PUB_LTD,
            contact_person='Er. Sunil Thapa',
            email='sunil@apex.com.np',
            phone='+977-9851000002',
            status=Client.Status.ONBOARDING,
            fiscal_year='2081/82',
            services=['STATUTORY_AUDIT', 'INTERNAL_AUDIT'],
            assigned_manager=self.user_a2,
        )

        self.client_a3 = Client.objects.create(
            firm=self.firm_a,
            name='Hari Gautam',
            business_name='Lumbini Organic Farm',
            pan_number='500123987',
            client_type=Client.ClientType.PROPRIETORSHIP,
            contact_person='Hari Gautam',
            email='hari@lumbinifarm.com.np',
            phone='+977-9851000003',
            status=Client.Status.INACTIVE,
            fiscal_year='2081/82',
            services=['BOOKKEEPING'],
        )

        # 4. Create Sample Client for Firm B
        self.client_b1 = Client.objects.create(
            firm=self.firm_b,
            name='Prem Gurung',
            business_name='Annapurna Treks Pvt Ltd',
            pan_number='609999999',
            client_type=Client.ClientType.PVT_LTD,
            contact_person='Prem Gurung',
            email='prem@annapurna.com.np',
            phone='+977-9856000001',
            status=Client.Status.ACTIVE,
            fiscal_year='2081/82',
            services=['TAX_VAT'],
            assigned_manager=self.user_b1,
        )

        # HTTP Clients
        self.http_a = HttpClient()
        self.http_a.force_login(self.user_a1)

        self.http_b = HttpClient()
        self.http_b.force_login(self.user_b1)

    # -------------------------------------------------------------
    # 1. Multi-Tenant Isolation Tests
    # -------------------------------------------------------------
    def test_client_list_tenant_scoped(self):
        """Firm A user sees Firm A clients only; Firm B clients never leak."""
        response = self.http_a.get(reverse('clients:client_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Himalayan Traders Pvt Ltd')
        self.assertContains(response, 'Apex Hydropower Ltd')
        self.assertNotContains(response, 'Annapurna Treks Pvt Ltd')

        # Firm B user sees only Firm B clients
        response_b = self.http_b.get(reverse('clients:client_list'))
        self.assertEqual(response_b.status_code, 200)
        self.assertContains(response_b, 'Annapurna Treks Pvt Ltd')
        self.assertNotContains(response_b, 'Himalayan Traders Pvt Ltd')

    def test_client_detail_cross_tenant_isolation_404(self):
        """Firm B user cannot access Firm A client detail endpoint."""
        url = reverse('clients:client_detail_json', kwargs={'client_id': self.client_a1.id})
        response = self.http_b.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 404)

    def test_client_edit_cross_tenant_isolation_404(self):
        """Firm B user cannot edit Firm A client."""
        url = reverse('clients:client_edit', kwargs={'client_id': self.client_a1.id})
        response = self.http_b.post(url, {'name': 'Hacked Name'})
        self.assertEqual(response.status_code, 404)
        self.client_a1.refresh_from_db()
        self.assertNotEqual(self.client_a1.name, 'Hacked Name')

    def test_client_toggle_status_cross_tenant_isolation_404(self):
        """Firm B user cannot deactivate Firm A client."""
        url = reverse('clients:client_deactivate', kwargs={'client_id': self.client_a1.id})
        response = self.http_b.post(url)
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------------------
    # 2. Search Functionality Tests
    # -------------------------------------------------------------
    def test_search_by_business_name(self):
        response = self.http_a.get(reverse('clients:client_list'), {'q': 'Apex'})
        self.assertContains(response, 'Apex Hydropower Ltd')
        self.assertNotContains(response, 'Himalayan Traders Pvt Ltd')

    def test_search_by_contact_name(self):
        response = self.http_a.get(reverse('clients:client_list'), {'q': 'Sunil Thapa'})
        self.assertContains(response, 'Apex Hydropower Ltd')
        self.assertNotContains(response, 'Himalayan Traders Pvt Ltd')

    def test_search_by_pan(self):
        response = self.http_a.get(reverse('clients:client_list'), {'q': '601928374'})
        self.assertContains(response, 'Himalayan Traders Pvt Ltd')
        self.assertNotContains(response, 'Apex Hydropower Ltd')

    def test_search_by_email(self):
        response = self.http_a.get(reverse('clients:client_list'), {'q': 'ramesh@himalayan.com.np'})
        self.assertContains(response, 'Himalayan Traders Pvt Ltd')
        self.assertNotContains(response, 'Apex Hydropower Ltd')

    def test_search_by_phone(self):
        response = self.http_a.get(reverse('clients:client_list'), {'q': '9851000001'})
        self.assertContains(response, 'Himalayan Traders Pvt Ltd')
        self.assertNotContains(response, 'Apex Hydropower Ltd')

    # -------------------------------------------------------------
    # 3. Filters Functionality Tests
    # -------------------------------------------------------------
    def test_filter_by_status(self):
        # Filter Active
        response_active = self.http_a.get(reverse('clients:client_list'), {'status': 'ACTIVE'})
        self.assertContains(response_active, 'Himalayan Traders Pvt Ltd')
        self.assertNotContains(response_active, 'Apex Hydropower Ltd')
        self.assertNotContains(response_active, 'Lumbini Organic Farm')

        # Filter Onboarding
        response_onb = self.http_a.get(reverse('clients:client_list'), {'status': 'ONBOARDING'})
        self.assertContains(response_onb, 'Apex Hydropower Ltd')
        self.assertNotContains(response_onb, 'Himalayan Traders Pvt Ltd')

        # Filter Inactive
        response_inact = self.http_a.get(reverse('clients:client_list'), {'status': 'INACTIVE'})
        self.assertContains(response_inact, 'Lumbini Organic Farm')
        self.assertNotContains(response_inact, 'Himalayan Traders Pvt Ltd')

    def test_filter_by_service(self):
        response = self.http_a.get(reverse('clients:client_list'), {'service': 'INTERNAL_AUDIT'})
        self.assertContains(response, 'Apex Hydropower Ltd')
        self.assertNotContains(response, 'Himalayan Traders Pvt Ltd')

    def test_filter_by_assigned_staff(self):
        response = self.http_a.get(reverse('clients:client_list'), {'assigned_to': str(self.user_a2.id)})
        # User A2 is assigned manager of client_a2 and staff on client_a1
        self.assertContains(response, 'Apex Hydropower Ltd')
        self.assertContains(response, 'Himalayan Traders Pvt Ltd')
        self.assertNotContains(response, 'Lumbini Organic Farm')

    def test_filter_by_business_type(self):
        response = self.http_a.get(reverse('clients:client_list'), {'client_type': 'PUB_LTD'})
        self.assertContains(response, 'Apex Hydropower Ltd')
        self.assertNotContains(response, 'Himalayan Traders Pvt Ltd')

    # -------------------------------------------------------------
    # 4. Client Creation & Onboarding Tasks Tests
    # -------------------------------------------------------------
    def test_client_creation_with_onboarding_tasks_and_audit(self):
        data = {
            'name': 'Gyanendra Shrestha',
            'business_name': 'Kathmandu Breweries Pvt Ltd',
            'pan_number': '602938475',
            'client_type': 'PVT_LTD',
            'email': 'gyan@ktmbrew.com.np',
            'phone': '+977-9841223344',
            'address': 'Ward 3, Baluwatar',
            'city': 'Kathmandu',
            'fiscal_year': '2081/82',
            'services': ['STATUTORY_AUDIT', 'TAX_VAT'],
            'assigned_manager': str(self.user_a1.id),
            'assigned_staff': [str(self.user_a2.id)],
            'create_onboarding_tasks': 'true',
            'status': 'ACTIVE',
        }
        response = self.http_a.post(reverse('clients:client_create'), data)
        self.assertRedirects(response, reverse('clients:client_list'))

        # Verify Client saved in DB
        new_client = Client.objects.filter(firm=self.firm_a, pan_number='602938475').first()
        self.assertIsNotNone(new_client)
        self.assertEqual(new_client.business_name, 'Kathmandu Breweries Pvt Ltd')
        self.assertEqual(new_client.assigned_manager, self.user_a1)
        self.assertTrue(new_client.assigned_staff.filter(id=self.user_a2.id).exists())
        self.assertIn('STATUTORY_AUDIT', new_client.services)

        # Verify 3 Onboarding tasks created
        tasks = Task.objects.filter(firm=self.firm_a, client=new_client)
        self.assertEqual(tasks.count(), 3)

        # Verify ClientActivity created
        activity = ClientActivity.objects.filter(client=new_client, activity_type=ClientActivity.ActivityType.NEW_CLIENT).first()
        self.assertIsNotNone(activity)

        # Verify AuditLog created
        audit = AuditLog.objects.filter(firm=self.firm_a, object_type='Client', object_id=str(new_client.id), action='CREATE').first()
        self.assertIsNotNone(audit)

    # -------------------------------------------------------------
    # 5. Client Detail JSON API Tests
    # -------------------------------------------------------------
    def test_client_detail_json_response(self):
        url = reverse('clients:client_detail_json', kwargs={'client_id': self.client_a1.id})
        response = self.http_a.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['business_name'], 'Himalayan Traders Pvt Ltd')
        self.assertEqual(data['pan_number'], '601928374')
        self.assertEqual(data['assigned_manager']['name'], 'Suyog Dhakal')
        self.assertEqual(len(data['assigned_staff']), 1)

    # -------------------------------------------------------------
    # 6. Action: Edit Client
    # -------------------------------------------------------------
    def test_client_edit_success(self):
        url = reverse('clients:client_edit', kwargs={'client_id': self.client_a1.id})
        data = {
            'name': 'Ramesh Adhikari Updated',
            'business_name': 'Himalayan Traders International Pvt Ltd',
            'pan_number': '601928374',
            'client_type': 'PVT_LTD',
            'email': 'ramesh_new@himalayan.com.np',
            'phone': '+977-9851000001',
            'address': 'Ward 28, Putalisadak',
            'city': 'Kathmandu',
            'status': 'ACTIVE',
            'fiscal_year': '2081/82',
            'services': ['STATUTORY_AUDIT', 'TAX_VAT', 'ADVISORY'],
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, reverse('clients:client_list'))

        self.client_a1.refresh_from_db()
        self.assertEqual(self.client_a1.business_name, 'Himalayan Traders International Pvt Ltd')
        self.assertIn('ADVISORY', self.client_a1.services)

        # Audit log recorded
        audit = AuditLog.objects.filter(firm=self.firm_a, object_type='Client', object_id=str(self.client_a1.id), action='UPDATE').first()
        self.assertIsNotNone(audit)

    # -------------------------------------------------------------
    # 7. Action: Assign Staff
    # -------------------------------------------------------------
    def test_client_assign_staff_success(self):
        url = reverse('clients:client_assign_staff', kwargs={'client_id': self.client_a3.id})
        data = {
            'assigned_manager': str(self.user_a2.id),
            'assigned_staff': [str(self.user_a1.id)],
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, reverse('clients:client_list'))

        self.client_a3.refresh_from_db()
        self.assertEqual(self.client_a3.assigned_manager, self.user_a2)
        self.assertTrue(self.client_a3.assigned_staff.filter(id=self.user_a1.id).exists())

        # ClientActivity recorded
        act = ClientActivity.objects.filter(client=self.client_a3, activity_type=ClientActivity.ActivityType.STAFF_ASSIGNED).first()
        self.assertIsNotNone(act)

    # -------------------------------------------------------------
    # 8. Action: Request Documents
    # -------------------------------------------------------------
    def test_client_request_document_success(self):
        url = reverse('clients:client_request_document', kwargs={'client_id': self.client_a1.id})
        due = timezone.localdate() + timedelta(days=7)
        data = {
            'requested_documents': 'Bank Statement & Monthly VAT Ledger',
            'due_date': str(due),
            'notes': 'Please send stamped copies in PDF format.',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, reverse('clients:client_list'))

        doc_req = DocumentRequest.objects.filter(firm=self.firm_a, client=self.client_a1).first()
        self.assertIsNotNone(doc_req)
        self.assertEqual(doc_req.requested_documents, 'Bank Statement & Monthly VAT Ledger')
        self.assertEqual(doc_req.due_date, due)

    # -------------------------------------------------------------
    # 9. Action: Create Task
    # -------------------------------------------------------------
    def test_client_create_task_success(self):
        url = reverse('clients:client_create_task', kwargs={'client_id': self.client_a1.id})
        due = timezone.localdate() + timedelta(days=5)
        data = {
            'title': 'Section 99 Advance Tax Filing Check',
            'assigned_to': str(self.user_a2.id),
            'priority': 'HIGH',
            'due_date': str(due),
            'description': 'Reconcile tax credit against IRD portal ledger.',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, reverse('clients:client_list'))

        task = Task.objects.filter(firm=self.firm_a, client=self.client_a1, title='Section 99 Advance Tax Filing Check').first()
        self.assertIsNotNone(task)
        self.assertEqual(task.assigned_to, self.user_a2)
        self.assertEqual(task.priority, Task.Priority.HIGH)

    # -------------------------------------------------------------
    # 10. Action: Send Message
    # -------------------------------------------------------------
    def test_client_send_message_success(self):
        url = reverse('clients:client_send_message', kwargs={'client_id': self.client_a1.id})
        data = {
            'subject': 'TDS Certificate for FY 2081/82 Q1',
            'body': 'Please provide the tax deducted at source certificates for contractor payments.',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, reverse('clients:client_list'))

        conv = Conversation.objects.filter(firm=self.firm_a, client=self.client_a1, title='TDS Certificate for FY 2081/82 Q1').first()
        self.assertIsNotNone(conv)
        self.assertTrue(conv.participants.filter(id=self.user_a1.id).exists())

        msg = ChatMessage.objects.filter(conversation=conv).first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.sender, self.user_a1)

    # -------------------------------------------------------------
    # 11. Action: Deactivate & Activate Status Toggle
    # -------------------------------------------------------------
    def test_client_deactivate_and_reactivate(self):
        url = reverse('clients:client_deactivate', kwargs={'client_id': self.client_a1.id})

        # Initially ACTIVE -> Toggle to INACTIVE
        self.assertEqual(self.client_a1.status, Client.Status.ACTIVE)
        response = self.http_a.post(url)
        self.assertRedirects(response, reverse('clients:client_list'))

        self.client_a1.refresh_from_db()
        self.assertEqual(self.client_a1.status, Client.Status.INACTIVE)
        self.assertFalse(self.client_a1.is_active)

        # Toggle back to ACTIVE
        response2 = self.http_a.post(url)
        self.assertRedirects(response2, reverse('clients:client_list'))

        self.client_a1.refresh_from_db()
        self.assertEqual(self.client_a1.status, Client.Status.ACTIVE)
        self.assertTrue(self.client_a1.is_active)

    # -------------------------------------------------------------
    # 12. Action: Export CSV
    # -------------------------------------------------------------
    def test_client_export_csv(self):
        url = reverse('clients:client_export')
        response = self.http_a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8-sig')

        content = response.content.decode('utf-8-sig')
        self.assertIn('Himalayan Traders Pvt Ltd', content)
        self.assertIn('Apex Hydropower Ltd', content)
        self.assertIn('601928374', content)
        self.assertNotIn('Annapurna Treks Pvt Ltd', content)  # Firm B client must not be in export

        # Verify audit log recorded
        audit = AuditLog.objects.filter(firm=self.firm_a, action=AuditLog.ActionType.EXPORT, object_type='Client').first()
        self.assertIsNotNone(audit)

    # -------------------------------------------------------------
    # 13. Empty State Rendering
    # -------------------------------------------------------------
    def test_empty_state_rendering(self):
        # Create an empty firm
        empty_firm = Firm.objects.create(name='Brand New CA Practice', slug='brand-new-ca')
        user_empty = User.objects.create_user('new@practice.com.np', 'Password123!', first_name='New')
        FirmMembership.objects.create(user=user_empty, firm=empty_firm, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)

        http_empty = HttpClient()
        http_empty.force_login(user_empty)

        response = http_empty.get(reverse('clients:client_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No clients yet')
        self.assertContains(response, 'Add your first client')


class ClientDetailPageTests(TestCase):
    """
    Comprehensive test suite for the Production-Quality Client Detail Page (/clients/<id>/).
    Verifies:
    1. Route /clients/<id>/
    2. Strict multi-tenant security verification: User -> Firm -> Client (never trust URL IDs alone)
    3. Header contents (Client name, Business name, PAN, Status, Actions)
    4. Overview cards (Client Info, Business Info, Team by 4 Roles, Active Services, Upcoming Deadlines)
    5. All 8 tabs load real data (Overview, Services, Tasks, Documents, Compliance, Billing, Messages, Activity)
    6. All reusable modal actions are functional (Edit, Assign Staff, Create Task, Request Documents, Deactivate, Upload Doc, Create Invoice, Task Toggle)
    """
    def setUp(self):
        # 1. Firm A & Practice Members across all 4 tiers (CA, Senior, Accountant, Staff)
        self.firm_a = Firm.objects.create(name='Dhakal & Associates', slug='dhakal-assoc')
        self.ca_user = User.objects.create_user('suyog@dhakal.com.np', 'Password123!', first_name='Suyog', last_name='Dhakal', ican_membership_no='FCA-1420')
        self.senior_user = User.objects.create_user('pooja@dhakal.com.np', 'Password123!', first_name='Pooja', last_name='Regmi')
        self.accountant_user = User.objects.create_user('ramesh@dhakal.com.np', 'Password123!', first_name='Ramesh', last_name='Shrestha')
        self.staff_user = User.objects.create_user('bikash@dhakal.com.np', 'Password123!', first_name='Bikash', last_name='Karki')

        FirmMembership.objects.create(user=self.ca_user, firm=self.firm_a, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.senior_user, firm=self.firm_a, role=FirmRole.SENIOR, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.accountant_user, firm=self.firm_a, role=FirmRole.ACCOUNTANT, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.staff_user, firm=self.firm_a, role=FirmRole.STAFF, status=MembershipStatus.ACTIVE)

        # 2. Firm B (Cross-Tenant Intruder Test)
        self.firm_b = Firm.objects.create(name='Pokhara Tax Partners', slug='pokhara-tax')
        self.user_b = User.objects.create_user('intruder@pokhara.com.np', 'Password123!', first_name='Intruder')
        FirmMembership.objects.create(user=self.user_b, firm=self.firm_b, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)

        # 3. Client in Firm A
        self.client_a = Client.objects.create(
            firm=self.firm_a,
            name='Ramesh Adhikari',
            business_name='Apex Hydropower Development Ltd',
            pan_number='300481920',
            registration_number='OCR-19284/074',
            client_type=Client.ClientType.PUB_LTD,
            contact_person='Ramesh Adhikari',
            email='ramesh@apex.com.np',
            phone='+977-9851000001',
            address='Ward No. 31, Shantinagar',
            city='Kathmandu',
            status=Client.Status.ACTIVE,
            fiscal_year='2081/82',
            services=['STATUTORY_AUDIT', 'TAX_VAT', 'OCR_COMPLIANCE'],
            assigned_manager=self.ca_user,
        )
        self.client_a.assigned_staff.add(self.senior_user, self.accountant_user, self.staff_user)

        # 4. Client in Firm B
        self.client_b = Client.objects.create(
            firm=self.firm_b,
            name='Hari Sharma',
            business_name='Annapurna Treks Pvt Ltd',
            pan_number='602918273',
            status=Client.Status.ACTIVE,
        )

        # 5. Populate related real data across all tabs for Client A
        today = timezone.localdate()

        # Tasks
        self.task1 = Task.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Verify Fixed Asset Register against NFRS Depreciation',
            description='Audit sample of turbine equipment and verify block ceiling rates.',
            assigned_to=self.senior_user,
            priority=Task.Priority.URGENT,
            status=Task.Status.IN_PROGRESS,
            due_date=today + timedelta(days=2),
        )

        # Compliance
        self.comp1 = ComplianceDeadline.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Monthly VAT Return (Ashoj 2081)',
            governing_act=ComplianceDeadline.GoverningAct.VAT,
            due_date_bs='2081-07-25',
            due_date_ad=today + timedelta(days=3),
            status=ComplianceDeadline.Status.DUE_SOON,
            notes='Section 19 VAT Act 2052',
            assigned_to=self.staff_user,
        )

        # Invoices
        from billing.models import Invoice
        from decimal import Decimal
        self.inv1 = Invoice.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            invoice_number='2081-001',
            subtotal_npr=Decimal('50000.00'),
            vat_percent=Decimal('13.00'),
            vat_amount_npr=Decimal('6500.00'),
            total_amount_npr=Decimal('56500.00'),
            paid_amount_npr=Decimal('20000.00'),
            status=Invoice.Status.PARTIAL,
            issue_date=today - timedelta(days=10),
            due_date=today + timedelta(days=20),
        )

        # Document Request
        self.doc_req1 = DocumentRequest.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            requested_documents='Bank Confirmation Letters & Loan Sanctions',
            due_date=today + timedelta(days=7),
            status=DocumentRequest.Status.PENDING,
            requested_by=self.ca_user,
            notes='Official signed copies required.',
        )

        # Conversation & Message
        self.conv1 = Conversation.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Regarding FY 2080/81 Final Audit Report',
        )
        self.conv1.participants.add(self.ca_user, self.senior_user)
        ChatMessage.objects.create(
            firm=self.firm_a,
            conversation=self.conv1,
            sender=self.ca_user,
            body='Please review the draft Annexure 7 disclosures before partner sign-off.',
        )

        # Activity
        self.act1 = ClientActivity.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            activity_type=ClientActivity.ActivityType.NEW_CLIENT,
            description='Client Apex Hydropower registered and onboarded.',
            performed_by=self.ca_user,
        )

        # HTTP Clients
        self.http_a = HttpClient()
        self.http_a.force_login(self.ca_user)

        self.http_b = HttpClient()
        self.http_b.force_login(self.user_b)

    # -------------------------------------------------------------
    # 1. Route & Security (User -> Firm -> Client)
    # -------------------------------------------------------------
    def test_client_detail_route_success(self):
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_a.id})
        response = self.http_a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'clients/client_detail.html')
        self.assertEqual(response.context['client'], self.client_a)

    def test_security_cross_tenant_access_denied(self):
        """
        Firm B user cannot access Firm A client by guessing/manipulating URL ID alone.
        Must return 404 (not found in firm).
        """
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_a.id})
        response = self.http_b.get(url)
        self.assertEqual(response.status_code, 404)

    def test_security_unauthenticated_redirects_to_login(self):
        anon_client = HttpClient()
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_a.id})
        response = anon_client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    # -------------------------------------------------------------
    # 2. Header Elements Verification
    # -------------------------------------------------------------
    def test_header_elements_rendered(self):
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_a.id})
        response = self.http_a.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Client name & Business name
        self.assertIn('Ramesh Adhikari', content)
        self.assertIn('Apex Hydropower Development Ltd', content)
        # PAN
        self.assertIn('300481920', content)
        # Status
        self.assertIn('Active', content)
        # Action buttons
        self.assertIn('Edit', content)
        self.assertIn('Create Task', content)
        self.assertIn('Request Documents', content)
        self.assertIn('Message', content)
        self.assertIn('More', content)

    # -------------------------------------------------------------
    # 3. Overview Tab Cards Verification
    # -------------------------------------------------------------
    def test_overview_cards_rendered(self):
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_a.id})
        response = self.http_a.get(url)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        # Client Information card
        self.assertIn('Client Information', content)
        self.assertIn('ramesh@apex.com.np', content)
        self.assertIn('+977-9851000001', content)
        self.assertIn('Ward No. 31, Shantinagar', content)

        # Business Information card
        self.assertIn('Business Information', content)
        self.assertIn('Public Limited Company', content)
        self.assertIn('OCR-19284/074', content)
        self.assertIn('2081/82', content)

        # Team by 4 Roles
        self.assertIn('Assigned Engagement Team', content)
        self.assertIn('Suyog Dhakal', content)     # CA
        self.assertIn('Pooja Regmi', content)      # Senior
        self.assertIn('Ramesh Shrestha', content)  # Accountant
        self.assertIn('Bikash Karki', content)     # Staff

        # Active Services card
        self.assertIn('Statutory Audit', content)
        self.assertIn('Tax &amp; VAT Compliance', content)


        # Upcoming Deadlines card
        self.assertIn('Monthly VAT Return (Ashoj 2081)', content)

    # -------------------------------------------------------------
    # 4. All 8 Tabs Data Verification
    # -------------------------------------------------------------
    def test_all_8_tabs_rendered_with_real_data(self):
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_a.id})
        response = self.http_a.get(url)
        self.assertEqual(response.status_code, 200)

        # Verify context contains real data across all tabs
        context = response.context
        self.assertIsNotNone(context['team_by_role'])
        self.assertGreater(len(context['subscribed_services']), 0)
        self.assertGreater(context['all_tasks'].count(), 0)
        self.assertGreater(context['compliance_deadlines'].count(), 0)
        self.assertGreater(context['invoices'].count(), 0)
        self.assertGreater(context['conversations'].count(), 0)
        self.assertGreater(context['activities'].count(), 0)
        self.assertGreater(context['document_requests'].count(), 0)

        # Verify tab badges/labels
        content = response.content.decode()
        self.assertIn('data-tab-target="overview"', content)
        self.assertIn('data-tab-target="services"', content)
        self.assertIn('data-tab-target="tasks"', content)
        self.assertIn('data-tab-target="documents"', content)
        self.assertIn('data-tab-target="compliance"', content)
        self.assertIn('data-tab-target="billing"', content)
        self.assertIn('data-tab-target="messages"', content)
        self.assertIn('data-tab-target="activity"', content)

    # -------------------------------------------------------------
    # 5. Modal Action: Edit Client
    # -------------------------------------------------------------
    def test_edit_client_action_functional(self):
        url = reverse('clients:client_edit', kwargs={'client_id': self.client_a.id})
        data = {
            'business_name': 'Apex Hydropower Corporation Ltd',
            'name': 'Er. Ramesh Adhikari',
            'contact_person': 'Er. Ramesh Adhikari',
            'client_type': Client.ClientType.PUB_LTD,
            'pan_number': '300481920',
            'registration_number': 'OCR-99999/075',
            'fiscal_year': '2081/82',
            'email': 'contact@apexcorp.com.np',
            'phone': '+977-1-4499112',
            'city': 'Kathmandu',
            'status': Client.Status.ACTIVE,
            'next': f'/clients/{self.client_a.id}/',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, f'/clients/{self.client_a.id}/')

        self.client_a.refresh_from_db()
        self.assertEqual(self.client_a.business_name, 'Apex Hydropower Corporation Ltd')
        self.assertEqual(self.client_a.registration_number, 'OCR-99999/075')

        # Verify activity logged
        act = ClientActivity.objects.filter(client=self.client_a, activity_type=ClientActivity.ActivityType.STATUS_CHANGED).first()
        self.assertIsNotNone(act)

    # -------------------------------------------------------------
    # 6. Modal Action: Assign Staff
    # -------------------------------------------------------------
    def test_assign_staff_action_functional(self):
        url = reverse('clients:client_assign_staff', kwargs={'client_id': self.client_a.id})
        data = {
            'assigned_manager': self.ca_user.id,
            'assigned_staff': [self.senior_user.id, self.accountant_user.id],
            'next': f'/clients/{self.client_a.id}/',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, f'/clients/{self.client_a.id}/')

        self.client_a.refresh_from_db()
        self.assertEqual(self.client_a.assigned_manager, self.ca_user)
        self.assertEqual(self.client_a.assigned_staff.count(), 2)

        # Verify activity logged
        act = ClientActivity.objects.filter(client=self.client_a, activity_type=ClientActivity.ActivityType.STAFF_ASSIGNED).first()
        self.assertIsNotNone(act)

    # -------------------------------------------------------------
    # 7. Modal Action: Create Task
    # -------------------------------------------------------------
    def test_create_task_action_functional(self):
        url = reverse('clients:client_create_task', kwargs={'client_id': self.client_a.id})
        data = {
            'title': 'Verify Tax Assessment Order FY 2079/80',
            'assigned_to': self.senior_user.id,
            'priority': Task.Priority.HIGH,
            'due_date': '2026-10-25',
            'description': 'Review IRD Section 101 assessment order and identify disputable items.',
            'next': f'/clients/{self.client_a.id}/?tab=tasks',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, f'/clients/{self.client_a.id}/?tab=tasks')

        new_task = Task.objects.filter(client=self.client_a, title='Verify Tax Assessment Order FY 2079/80').first()
        self.assertIsNotNone(new_task)
        self.assertEqual(new_task.priority, Task.Priority.HIGH)
        self.assertEqual(new_task.firm, self.firm_a)

    # -------------------------------------------------------------
    # 8. Modal Action: Request Document
    # -------------------------------------------------------------
    def test_request_document_action_functional(self):
        url = reverse('clients:client_request_document', kwargs={'client_id': self.client_a.id})
        data = {
            'requested_documents': 'Trial Balance and Fixed Asset Schedule',
            'due_date': '2026-10-30',
            'notes': 'Provide signed Excel sheet.',
            'next': f'/clients/{self.client_a.id}/?tab=documents',
        }
        response = self.http_a.post(url, data)
        self.assertRedirects(response, f'/clients/{self.client_a.id}/?tab=documents')

        doc_req = DocumentRequest.objects.filter(client=self.client_a, requested_documents='Trial Balance and Fixed Asset Schedule').first()
        self.assertIsNotNone(doc_req)
        self.assertEqual(doc_req.firm, self.firm_a)

    # -------------------------------------------------------------
    # 9. Modal Action: Deactivate / Reactivate
    # -------------------------------------------------------------
    def test_deactivate_client_action_functional(self):
        url = reverse('clients:client_deactivate', kwargs={'client_id': self.client_a.id})
        data = {'next': f'/clients/{self.client_a.id}/'}

        # Deactivate
        response = self.http_a.post(url, data)
        self.assertRedirects(response, f'/clients/{self.client_a.id}/')

        self.client_a.refresh_from_db()
        self.assertEqual(self.client_a.status, Client.Status.INACTIVE)
        self.assertFalse(self.client_a.is_active)

        # Reactivate
        response2 = self.http_a.post(url, data)
        self.assertRedirects(response2, f'/clients/{self.client_a.id}/')

        self.client_a.refresh_from_db()
        self.assertEqual(self.client_a.status, Client.Status.ACTIVE)
        self.assertTrue(self.client_a.is_active)

    # -------------------------------------------------------------
    # 10. Action: Task Completion Toggle
    # -------------------------------------------------------------
    def test_task_toggle_completion_functional(self):
        url = reverse('clients:client_task_toggle', kwargs={'client_id': self.client_a.id, 'task_id': self.task1.id})

        # Toggle to Completed
        response = self.http_a.post(url)
        self.assertRedirects(response, f'/clients/{self.client_a.id}/?tab=tasks')

        self.task1.refresh_from_db()
        self.assertEqual(self.task1.status, Task.Status.COMPLETED)
        self.assertIsNotNone(self.task1.completed_at)

        # Toggle back to Incomplete
        response2 = self.http_a.post(url)
        self.assertRedirects(response2, f'/clients/{self.client_a.id}/?tab=tasks')

        self.task1.refresh_from_db()
        self.assertEqual(self.task1.status, Task.Status.TODO)
        self.assertIsNone(self.task1.completed_at)


class ClientProductionCRUDAndArchiveTests(TestCase):
    """
    Tests for Client CRUD, extended CA data fields, archiving, and restoration.
    """
    def setUp(self):
        self.firm = Firm.objects.create(name='Global CA Associates', slug='global-ca')
        self.user_ca = User.objects.create_user('ca@globalca.com', 'Pass123!@#', first_name='Suresh', last_name='Pradhan')
        self.user_staff = User.objects.create_user('staff@globalca.com', 'Pass123!@#', first_name='Rohan', last_name='Shrestha')
        FirmMembership.objects.create(user=self.user_ca, firm=self.firm, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.user_staff, firm=self.firm, role=FirmRole.STAFF, status=MembershipStatus.ACTIVE)

        self.client = HttpClient()
        self.client.force_login(self.user_ca)

    def test_create_client_with_extended_fields(self):
        url = reverse('clients:client_create')
        data = {
            'name': 'Bikram Khadka',
            'business_name': 'Khadka Engineering Solutions',
            'legal_name': 'Khadka Engineering Solutions Pvt. Ltd.',
            'pan_number': '601827364',
            'registration_number': '109283/080/081',
            'client_type': Client.ClientType.PVT_LTD,
            'contact_person': 'Bikram Khadka',
            'email': 'info@khadkaeng.com.np',
            'phone': '+977-9841234567',
            'address': 'Putalisadak, Ward 28',
            'city': 'Kathmandu',
            'registration_date': '2023-04-15',
            'tax_registration_date': '2023-05-01',
            'notes': 'Key corporate client for annual audit and VAT filings.',
            'fiscal_year': '2081/82',
            'services': ['STATUTORY_AUDIT', 'TAX_VAT'],
            'assigned_manager': str(self.user_ca.id),
            'assigned_staff': [str(self.user_staff.id)],
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        created_client = Client.objects.filter(firm=self.firm, pan_number='601827364').first()
        self.assertIsNotNone(created_client)
        self.assertEqual(created_client.legal_name, 'Khadka Engineering Solutions Pvt. Ltd.')
        self.assertEqual(created_client.display_legal_name, 'Khadka Engineering Solutions Pvt. Ltd.')
        self.assertEqual(created_client.display_business_name, 'Khadka Engineering Solutions')
        self.assertEqual(str(created_client.registration_date), '2023-04-15')
        self.assertEqual(str(created_client.tax_registration_date), '2023-05-01')
        self.assertIn('VAT filings', created_client.notes)
        self.assertEqual(created_client.assigned_manager, self.user_ca)
        self.assertIn(self.user_staff, created_client.assigned_staff.all())

    def test_edit_client_with_extended_fields(self):
        client_obj = Client.objects.create(
            firm=self.firm,
            name='Original Name',
            business_name='Original Business',
            legal_name='Original Legal Name',
            pan_number='123456789',
            status=Client.Status.ACTIVE,
        )
        url = reverse('clients:client_edit', kwargs={'client_id': client_obj.id})
        data = {
            'name': 'Updated Signatory',
            'business_name': 'Updated Trading Name',
            'legal_name': 'Updated Legal Entity Pvt Ltd',
            'pan_number': '123456789',
            'registration_number': 'REG-999',
            'client_type': Client.ClientType.PVT_LTD,
            'contact_person': 'Updated Contact',
            'email': 'updated@client.com',
            'phone': '+977-9800000000',
            'address': 'New Baneshwor',
            'city': 'Kathmandu',
            'fiscal_year': '2081/82',
            'status': Client.Status.ACTIVE,
            'registration_date': '2024-01-10',
            'tax_registration_date': '2024-02-15',
            'notes': 'Updated engagement notes.',
            'services': ['BOOKKEEPING'],
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        client_obj.refresh_from_db()
        self.assertEqual(client_obj.legal_name, 'Updated Legal Entity Pvt Ltd')
        self.assertEqual(client_obj.business_name, 'Updated Trading Name')
        self.assertEqual(str(client_obj.registration_date), '2024-01-10')
        self.assertEqual(str(client_obj.tax_registration_date), '2024-02-15')
        self.assertEqual(client_obj.notes, 'Updated engagement notes.')

    def test_archive_and_restore_client(self):
        client_obj = Client.objects.create(
            firm=self.firm,
            name='Archivable Client',
            business_name='Archivable Business',
            pan_number='987654321',
            status=Client.Status.ACTIVE,
        )

        # 1. Archive
        archive_url = reverse('clients:client_archive', kwargs={'client_id': client_obj.id})
        resp_archive = self.client.post(archive_url)
        self.assertEqual(resp_archive.status_code, 302)

        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, Client.Status.ARCHIVED)
        self.assertFalse(client_obj.is_active)

        # Verify activity logged
        act_archive = ClientActivity.objects.filter(
            client=client_obj,
            activity_type=ClientActivity.ActivityType.CLIENT_ARCHIVED,
        ).first()
        self.assertIsNotNone(act_archive)

        # 2. Restore
        restore_url = reverse('clients:client_restore', kwargs={'client_id': client_obj.id})
        resp_restore = self.client.post(restore_url)
        self.assertEqual(resp_restore.status_code, 302)

        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, Client.Status.ACTIVE)
        self.assertTrue(client_obj.is_active)

        # Verify activity logged
        act_restore = ClientActivity.objects.filter(
            client=client_obj,
            activity_type=ClientActivity.ActivityType.CLIENT_RESTORED,
        ).first()
        self.assertIsNotNone(act_restore)

    def test_toggle_status_archive_and_restore(self):
        client_obj = Client.objects.create(
            firm=self.firm,
            name='Toggle Client',
            business_name='Toggle Corp',
            status=Client.Status.ACTIVE,
        )
        toggle_url = reverse('clients:client_toggle_status', kwargs={'client_id': client_obj.id})

        # Archive via toggle
        self.client.post(toggle_url, {'action': 'archive'})
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, Client.Status.ARCHIVED)

        # Restore via toggle
        self.client.post(toggle_url, {'action': 'restore'})
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, Client.Status.ACTIVE)


class ClientSearchAndFilterExtendedTests(TestCase):
    """
    Tests for comprehensive search and filtering capabilities.
    """
    def setUp(self):
        self.firm = Firm.objects.create(name='Apex CA Practice', slug='apex-ca')
        self.user_manager = User.objects.create_user('manager@apex.com', 'Pass123!', first_name='Pooja', last_name='Sharma')
        self.user_other = User.objects.create_user('other@apex.com', 'Pass123!', first_name='Kiran', last_name='KC')
        FirmMembership.objects.create(user=self.user_manager, firm=self.firm, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.user_other, firm=self.firm, role=FirmRole.CA, status=MembershipStatus.ACTIVE)

        self.c1 = Client.objects.create(
            firm=self.firm,
            name='Aayush Shrestha',
            business_name='Himalayan Organic Teas',
            legal_name='Himalayan Organic Teas Pvt Ltd',
            pan_number='111222333',
            client_type=Client.ClientType.PVT_LTD,
            email='aayush@himalayantea.com',
            phone='+977-9851111111',
            status=Client.Status.ACTIVE,
            assigned_manager=self.user_manager,
        )
        self.c2 = Client.objects.create(
            firm=self.firm,
            name='Deepak Karki',
            business_name='Everest Hydropower',
            legal_name='Everest Hydropower Development Co Ltd',
            pan_number='444555666',
            client_type=Client.ClientType.PUB_LTD,
            email='deepak@everesthydro.com',
            phone='+977-9852222222',
            status=Client.Status.ONBOARDING,
            assigned_manager=self.user_other,
        )
        self.c3 = Client.objects.create(
            firm=self.firm,
            name='Sunita Rai',
            business_name='Rai Medical Supplies',
            legal_name='Rai Medical Supplies Enterprise',
            pan_number='777888999',
            client_type=Client.ClientType.PROPRIETORSHIP,
            email='sunita@raimedical.com',
            phone='+977-9853333333',
            status=Client.Status.ARCHIVED,
            is_active=False,
        )

        self.client = HttpClient()
        self.client.force_login(self.user_manager)

    def test_search_by_legal_name(self):
        url = reverse('clients:client_list') + '?q=Development'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        clients = list(response.context['clients'])
        self.assertIn(self.c2, clients)
        self.assertNotIn(self.c1, clients)

    def test_search_by_pan(self):
        url = reverse('clients:client_list') + '?q=111222333'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        clients = list(response.context['clients'])
        self.assertEqual(clients, [self.c1])

    def test_search_by_phone_and_email(self):
        # Email search
        url_email = reverse('clients:client_list') + '?q=deepak@everesthydro'
        resp_email = self.client.get(url_email)
        self.assertIn(self.c2, list(resp_email.context['clients']))

        # Phone search
        url_phone = reverse('clients:client_list') + '?q=9851111111'
        resp_phone = self.client.get(url_phone)
        self.assertIn(self.c1, list(resp_phone.context['clients']))

    def test_filter_by_archived_status(self):
        url = reverse('clients:client_list') + '?status=ARCHIVED'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        clients = list(response.context['clients'])
        self.assertIn(self.c3, clients)
        self.assertNotIn(self.c1, clients)
        self.assertNotIn(self.c2, clients)

    def test_filter_by_client_type(self):
        url = reverse('clients:client_list') + '?type=PUB_LTD'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        clients = list(response.context['clients'])
        self.assertIn(self.c2, clients)
        self.assertNotIn(self.c1, clients)

    def test_filter_by_assigned_staff(self):
        url = reverse('clients:client_list') + f'?manager={self.user_manager.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        clients = list(response.context['clients'])
        self.assertIn(self.c1, clients)
        self.assertNotIn(self.c2, clients)


class CrossFirmValidationAndSecurityTests(TestCase):
    """
    Tests ensuring strict firm/tenant boundaries and cross-firm attachment prevention.
    """
    def setUp(self):
        # Firm 1
        self.firm_1 = Firm.objects.create(name='Firm One', slug='firm-one')
        self.user_1 = User.objects.create_user('user1@firmone.com', 'Pass123!', first_name='Firm1', last_name='User')
        FirmMembership.objects.create(user=self.user_1, firm=self.firm_1, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        self.client_1 = Client.objects.create(
            firm=self.firm_1,
            name='Client One',
            business_name='Client One Corp',
            pan_number='111111111',
            status=Client.Status.ACTIVE,
        )

        # Firm 2
        self.firm_2 = Firm.objects.create(name='Firm Two', slug='firm-two')
        self.user_2 = User.objects.create_user('user2@firmtwo.com', 'Pass123!', first_name='Firm2', last_name='User')
        FirmMembership.objects.create(user=self.user_2, firm=self.firm_2, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        self.client_2 = Client.objects.create(
            firm=self.firm_2,
            name='Client Two',
            business_name='Client Two Corp',
            pan_number='222222222',
            status=Client.Status.ACTIVE,
        )

        self.http_user_1 = HttpClient()
        self.http_user_1.force_login(self.user_1)

        self.http_user_2 = HttpClient()
        self.http_user_2.force_login(self.user_2)

    def test_cross_firm_client_views_return_404(self):
        # User 1 cannot view Client 2
        resp_detail = self.http_user_1.get(reverse('clients:client_detail', kwargs={'client_id': self.client_2.id}))
        self.assertEqual(resp_detail.status_code, 404)

        # User 1 cannot edit Client 2
        resp_edit = self.http_user_1.post(reverse('clients:client_edit', kwargs={'client_id': self.client_2.id}), {'name': 'Hacked'})
        self.assertEqual(resp_edit.status_code, 404)

        # User 1 cannot archive Client 2
        resp_archive = self.http_user_1.post(reverse('clients:client_archive', kwargs={'client_id': self.client_2.id}))
        self.assertEqual(resp_archive.status_code, 404)

        # User 1 cannot restore Client 2
        resp_restore = self.http_user_1.post(reverse('clients:client_restore', kwargs={'client_id': self.client_2.id}))
        self.assertEqual(resp_restore.status_code, 404)

    def test_cross_firm_task_attachment_prevented(self):
        task = Task(firm=self.firm_1, client=self.client_2, title='Illegal Cross-firm Task')
        with self.assertRaises(ValidationError):
            task.clean()
        with self.assertRaises(ValueError):
            task.save()

    def test_cross_firm_invoice_attachment_prevented(self):
        invoice = Invoice(
            firm=self.firm_1,
            client=self.client_2,
            invoice_number='INV-CROSS-001',
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
            subtotal_npr=1000,
        )
        with self.assertRaises(ValidationError):
            invoice.clean()
        with self.assertRaises(ValueError):
            invoice.save()

    def test_cross_firm_document_attachment_prevented(self):
        doc = Document(
            firm=self.firm_1,
            client=self.client_2,
            title='Illegal Cross-firm Doc',
            category=Document.Category.TAX_FILING,
        )
        with self.assertRaises(ValidationError):
            doc.clean()
        with self.assertRaises(ValueError):
            doc.save()

    def test_cross_firm_calendar_event_attachment_prevented(self):
        event = CalendarEvent(
            firm=self.firm_1,
            client=self.client_2,
            title='Illegal Cross-firm Event',
            start_time=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            event.clean()
        with self.assertRaises(ValueError):
            event.save()

    def test_cross_firm_client_activity_attachment_prevented(self):
        activity = ClientActivity(
            firm=self.firm_1,
            client=self.client_2,
            activity_type=ClientActivity.ActivityType.TASK_COMPLETED,
            description='Illegal activity',
        )
        with self.assertRaises(ValidationError):
            activity.clean()
        with self.assertRaises(ValueError):
            activity.save()

    def test_cross_firm_staff_assignment_prevented(self):
        # Assigning user from firm 2 to client in firm 1
        self.client_1.assigned_manager = self.user_2
        with self.assertRaises(ValidationError):
            self.client_1.clean()


class ClientDetailWorkspaceNavigationTests(TestCase):
    """
    Tests ensuring all 8 client detail workspace tabs render correctly.
    """
    def setUp(self):
        self.firm = Firm.objects.create(name='Kathmandu Advisory', slug='ktm-advisory')
        self.user = User.objects.create_user('lead@ktm.com', 'Pass123!', first_name='Lead', last_name='Partner')
        FirmMembership.objects.create(user=self.user, firm=self.firm, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)

        self.client_obj = Client.objects.create(
            firm=self.firm,
            name='Test Signatory',
            business_name='Workspace Demo Client Pvt Ltd',
            pan_number='302918475',
            status=Client.Status.ACTIVE,
        )

        self.http_client = HttpClient()
        self.http_client.force_login(self.user)

    def test_all_workspace_tabs_rendered(self):
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_obj.id})
        response = self.http_client.get(url)
        self.assertEqual(response.status_code, 200)

        # Assert all 8 tabs
        required_tabs = ['overview', 'tasks', 'documents', 'compliance', 'calendar', 'billing', 'messages', 'activity']
        for tab in required_tabs:
            self.assertContains(response, f'data-tab-target="{tab}"')
            self.assertContains(response, f'id="panel-{tab}"')

    def test_create_client_calendar_event_functional(self):
        url = reverse('clients:client_create_event', kwargs={'client_id': self.client_obj.id})
        start_time = (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        end_time = (timezone.now() + timedelta(days=2, hours=2)).strftime('%Y-%m-%dT%H:%M')
        data = {
            'title': 'Statutory Audit Planning Meeting',
            'event_type': CalendarEvent.EventType.AUDIT_VISIT,
            'start_time': start_time,
            'end_time': end_time,
            'location': 'Client HQ Boardroom',
            'description': 'Discussion on audit scope, timeline, and preliminary documentation.',
            'next': f'/clients/{self.client_obj.id}/?tab=calendar',
        }
        response = self.http_client.post(url, data)
        self.assertRedirects(response, f'/clients/{self.client_obj.id}/?tab=calendar')

        created_event = CalendarEvent.objects.filter(client=self.client_obj, title='Statutory Audit Planning Meeting').first()
        self.assertIsNotNone(created_event)
        self.assertEqual(created_event.firm, self.firm)
        self.assertEqual(created_event.created_by, self.user)


