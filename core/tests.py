from django.test import TestCase, Client
from django.urls import reverse
from django.db import connection


class CAFlowFoundationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_postgresql_connection(self):
        """Verify direct connection and query execution on PostgreSQL database."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            self.assertEqual(row[0], 1)

    def test_public_routes(self):
        """Verify public landing page and login page render with status 200."""
        routes = [
            'core:landing',
            'accounts:login',
        ]
        for route_name in routes:
            response = self.client.get(reverse(route_name))
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
            # Ensure base layout tokens are present
            self.assertContains(response, "cf-sidebar")
            self.assertContains(response, "cf-topbar")

    def test_landing_page_content(self):
        """Verify required landing page content and copy specifications."""
        response = self.client.get(reverse('core:landing'))
        self.assertContains(response, "Run your CA firm from one powerful workspace.")
        self.assertContains(response, "Manage clients, documents, compliance workflows, tasks and communication from one secure platform.")
        self.assertContains(response, "Start Free")
        self.assertContains(response, "Book a Demo")

    def test_dashboard_metric_values(self):
        """Verify required fictional demo metric values on the dashboard."""
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, "128")  # Total Clients
        self.assertContains(response, "24")   # Pending Tasks
        self.assertContains(response, "8")    # Due Soon
        self.assertContains(response, "NPR 45K") # Outstanding Fees
        self.assertContains(response, "Today's Work")
        self.assertContains(response, "Upcoming Compliance")
        self.assertContains(response, "Document Requests")
        self.assertContains(response, "Team Workload")
        self.assertContains(response, "Recent Activity")
