import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client as TestClient, TestCase
from django.urls import reverse

from billing.models import Invoice
from clients.models import Client as ClientEntity
from core.services import seed_dashboard_demo_data
from documents.models import DocumentRequest
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus
from tasks.models import Task

User = get_user_model()


class CAFlowFoundationTests(TestCase):
    def setUp(self):
        self.client = TestClient()
        self.user = User.objects.create_user(
            email='testleader@caflow.com.np',
            password='Password123!',
            first_name='Test',
            last_name='Leader',
            is_active=True,
        )
        self.firm = Firm.objects.create(
            name='Test CA Practice',
            slug='test-ca-practice',
            email='info@testcapractice.com.np',
        )
        self.membership = FirmMembership.objects.create(
            user=self.user,
            firm=self.firm,
            role=FirmRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )

        # Authenticate self.client by default
        self.client.login(email='testleader@caflow.com.np', password='Password123!')
        session = self.client.session
        session['active_firm_id'] = str(self.firm.id)
        session.save()

    def test_postgresql_connection(self):
        """Verify direct connection and query execution on PostgreSQL database."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            self.assertEqual(row[0], 1)

    def test_public_routes(self):
        """Verify public landing page and login page render with status 200."""
        anon_client = TestClient()
        routes = [
            'core:landing',
            'accounts:login',
            'accounts:register',
        ]
        for route_name in routes:
            response = anon_client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, f"Route {route_name} failed with status {response.status_code}")
            self.assertContains(response, "CAFlow")

    def test_workspace_and_design_system_routes(self):
        """Verify all authenticated shell foundation routes render cleanly."""
        routes = [
            'core:dashboard',
            'core:design_system',
            'accounts:profile',
            'clients:client_list',
            'tasks:task_list',
            'documents:document_list',
            'compliance:compliance_list',
            'calendar_app:calendar_view',
            'messages_app:inbox',
            'notifications:notification_list',
            'billing:invoice_list',
            'reports:report_dashboard',
            'firms:team_list',
            'firms:firm_settings',
            'audit:audit_list',
        ]
        for route_name in routes:
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, f"Route {route_name} failed with status {response.status_code}")
            self.assertContains(response, "cf-sidebar")
            self.assertContains(response, "cf-topbar")

    def test_landing_page_content(self):
        """Verify required landing page content and copy specifications."""
        anon_client = TestClient()
        response = anon_client.get(reverse('core:landing'))
        self.assertContains(response, "Run your CA firm from one powerful workspace.")
        self.assertContains(response, "Manage clients, documents, compliance workflows, tasks and communication from one secure platform.")
        self.assertContains(response, "Start Free")
        self.assertContains(response, "Book a Demo")

    def test_dashboard_metric_values_when_seeded(self):
        """Verify required demo metric values when explicit demo data is seeded."""
        seed_dashboard_demo_data(firm=self.firm, user=self.user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "128")  # Total Clients
        self.assertContains(response, "24")   # Pending Tasks
        self.assertContains(response, "8")    # Due Soon
        self.assertContains(response, "NPR 45K") # Outstanding Fees
        self.assertContains(response, "Today's Work")
        self.assertContains(response, "Upcoming Compliance")
        self.assertContains(response, "Document Requests")
        self.assertContains(response, "Team Workload")
        self.assertContains(response, "Recent Activity")

    def test_dashboard_empty_state_for_fresh_firm(self):
        """Verify a fresh firm renders empty state metrics with 0 values without auto-seeding demo data."""
        fresh_firm = Firm.objects.create(name='Fresh CA Office', slug='fresh-ca')
        fresh_user = User.objects.create_user('freshca@test.com.np', 'Password123!', first_name='Fresh')
        FirmMembership.objects.create(user=fresh_user, firm=fresh_firm, role=FirmRole.OWNER)

        fresh_client = TestClient()
        fresh_client.login(email='freshca@test.com.np', password='Password123!')
        session = fresh_client.session
        session['active_firm_id'] = str(fresh_firm.id)
        session.save()

        response = fresh_client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        # Verify 0 counts
        self.assertEqual(ClientEntity.objects.filter(firm=fresh_firm).count(), 0)
        self.assertEqual(Task.objects.filter(firm=fresh_firm).count(), 0)
        self.assertContains(response, "Total Clients")
        self.assertContains(response, "Pending Tasks")
        self.assertContains(response, "NPR 0")

    def test_dashboard_header_and_greeting(self):
        """Verify dashboard header greeting, subtitle, date, and quick action dropdown."""
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Good morning,")
        self.assertContains(response, "Test Leader")
        self.assertContains(response, "Here's what's happening across your firm today.")
        self.assertContains(response, "Quick Action")
        self.assertContains(response, "Add Client")
        self.assertContains(response, "Create Task")
        self.assertContains(response, "Request Documents")
        self.assertContains(response, "Create Invoice")

    def test_dashboard_all_sections_and_fields(self):
        """Verify all required dashboard sections, columns, and data fields."""
        client = ClientEntity.objects.create(firm=self.firm, name='Apex Ltd', pan_number='123456789')
        Task.objects.create(firm=self.firm, client=client, title='VAT Filing', assigned_to=self.user)
        response = self.client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Stat cards
        self.assertContains(response, "Total Clients")
        self.assertContains(response, "Pending Tasks")
        self.assertContains(response, "Due Soon")
        self.assertContains(response, "Outstanding")

        # Today's Work Table columns
        self.assertContains(response, "Task")
        self.assertContains(response, "Client")
        self.assertContains(response, "Assigned To")
        self.assertContains(response, "Priority")
        self.assertContains(response, "Due Date")
        self.assertContains(response, "Status")
        self.assertContains(response, "Action")

        # Section headings
        self.assertContains(response, "Upcoming Compliance")
        self.assertContains(response, "Document Requests")
        self.assertContains(response, "Team Workload")
        self.assertContains(response, "Recent Activity")

    def test_unauthenticated_dashboard_redirects_to_login(self):
        """Unauthenticated user accessing /dashboard/ is redirected to login."""
        anon = TestClient()
        response = anon.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_unauthenticated_protected_modules_redirect_to_login(self):
        """Verify all protected workspace modules redirect unauthenticated requests to login."""
        anon = TestClient()
        protected_routes = [
            'documents:document_list',
            'compliance:compliance_list',
            'calendar_app:calendar_view',
            'messages_app:inbox',
            'notifications:notification_list',
            'billing:invoice_list',
            'reports:report_dashboard',
            'audit:audit_list',
        ]
        for route in protected_routes:
            resp = anon.get(reverse(route))
            self.assertEqual(resp.status_code, 302, f"Route {route} did not redirect unauthenticated user")
            self.assertIn(reverse('accounts:login'), resp.url)

    def test_quick_action_workflows(self):
        """Verify all quick action POST endpoints create corresponding Django model records."""
        # 1. Quick Add Client
        add_client_res = self.client.post(reverse('core:quick_add_client'), {
            'name': 'Gorkha Brewery Ltd',
            'pan_number': '609871234',
            'client_type': 'PUB_LTD',
            'contact_person': 'Surendra Shrestha',
            'email': 'finance@gorkhabrew.com.np',
            'city': 'Kathmandu',
        })
        self.assertEqual(add_client_res.status_code, 302)
        new_client = ClientEntity.objects.filter(firm=self.firm, pan_number='609871234').first()
        self.assertIsNotNone(new_client)
        self.assertEqual(new_client.firm, self.firm)

        # 2. Quick Create Task
        create_task_res = self.client.post(reverse('core:quick_create_task'), {
            'title': 'Excise Verification Q1',
            'client_id': str(new_client.id),
            'priority': 'HIGH',
            'due_date': '2026-10-15',
            'description': 'Check brewery output registers and excise stamp reconciliation.',
        })
        self.assertEqual(create_task_res.status_code, 302)
        new_task = Task.objects.filter(firm=self.firm, title='Excise Verification Q1').first()
        self.assertIsNotNone(new_task)
        self.assertEqual(new_task.firm, self.firm)

        # 3. Quick Request Documents
        req_doc_res = self.client.post(reverse('core:quick_request_documents'), {
            'client_id': str(new_client.id),
            'requested_documents': 'Excise duty payment receipts & stock ledgers',
            'due_date': '2026-10-18',
            'notes': 'Upload scanned copies before audit closing.',
        })
        self.assertEqual(req_doc_res.status_code, 302)
        new_doc_req = DocumentRequest.objects.filter(firm=self.firm, client=new_client).first()
        self.assertIsNotNone(new_doc_req)
        self.assertEqual(new_doc_req.firm, self.firm)

        # 4. Quick Create Invoice
        create_inv_res = self.client.post(reverse('core:quick_create_invoice'), {
            'client_id': str(new_client.id),
            'invoice_number': '2081-099',
            'subtotal_npr': '25000.00',
            'due_date': '2026-10-25',
        })
        self.assertEqual(create_inv_res.status_code, 302)
        new_inv = Invoice.objects.filter(firm=self.firm, invoice_number='2081-099').first()
        self.assertIsNotNone(new_inv)
        self.assertEqual(new_inv.total_amount_npr, Decimal('28250.00')) # 25000 + 13% VAT (3250)
        self.assertEqual(new_inv.firm, self.firm)

        # 5. Quick Complete Task
        complete_res = self.client.post(reverse('core:quick_complete_task', kwargs={'task_id': new_task.id}))
        self.assertEqual(complete_res.status_code, 302)
        new_task.refresh_from_db()
        self.assertEqual(new_task.status, Task.Status.COMPLETED)

        # 6. Quick Remind Document
        remind_res = self.client.post(reverse('core:quick_remind_document', kwargs={'req_id': new_doc_req.id}))
        self.assertEqual(remind_res.status_code, 302)
        new_doc_req.refresh_from_db()
        self.assertEqual(new_doc_req.status, DocumentRequest.Status.REMINDED)

    def test_quick_action_cross_tenant_isolation(self):
        """Firm A user cannot complete tasks or remind documents belonging to Firm B."""
        firm_b = Firm.objects.create(name='Firm B Practice', slug='firm-b-practice')
        user_b = User.objects.create_user('leader_b@firmb.com.np', 'Password123!')
        FirmMembership.objects.create(user=user_b, firm=firm_b, role=FirmRole.OWNER)

        client_b = ClientEntity.objects.create(firm=firm_b, name='Firm B Client')
        task_b = Task.objects.create(firm=firm_b, title='Firm B Task', client=client_b)
        doc_req_b = DocumentRequest.objects.create(
            firm=firm_b,
            client=client_b,
            requested_documents='Bank Statements',
            due_date=datetime.date.today(),
        )

        # Attempt to complete task_b from Firm A user
        res_complete = self.client.post(reverse('core:quick_complete_task', kwargs={'task_id': task_b.id}))
        self.assertEqual(res_complete.status_code, 404)
        task_b.refresh_from_db()
        self.assertEqual(task_b.status, Task.Status.TODO)

        # Attempt to remind doc_req_b from Firm A user
        res_remind = self.client.post(reverse('core:quick_remind_document', kwargs={'req_id': doc_req_b.id}))
        self.assertEqual(res_remind.status_code, 404)
        doc_req_b.refresh_from_db()
        self.assertEqual(doc_req_b.status, DocumentRequest.Status.PENDING)


