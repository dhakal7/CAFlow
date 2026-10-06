import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog
from clients.models import Client as ClientEntity
from firms.models import Firm, FirmInvitation, FirmMembership, FirmRole, MembershipStatus
from firms.permissions import has_firm_permission, get_user_firm_permissions
from firms.services import get_firm_object_or_404, switch_active_firm, create_firm_invitation
from tasks.models import Task, TaskChecklistItem

User = get_user_model()


class RolesAndPermissionsTests(TestCase):
    """
    Tests the server-side role and permission architecture:
    OWNER, ADMIN, CA, SENIOR, ACCOUNTANT, STAFF, and CLIENT.
    """
    def setUp(self):
        self.firm = Firm.objects.create(name='Alpha CA Practice', slug='alpha-ca')

        # Create users for each role
        self.owner = User.objects.create_user('owner@alpha.com.np', 'Password123!', first_name='Owner')
        self.admin = User.objects.create_user('admin@alpha.com.np', 'Password123!', first_name='Admin')
        self.ca = User.objects.create_user('ca@alpha.com.np', 'Password123!', first_name='CA')
        self.senior = User.objects.create_user('senior@alpha.com.np', 'Password123!', first_name='Senior')
        self.accountant = User.objects.create_user('accountant@alpha.com.np', 'Password123!', first_name='Accountant')
        self.staff = User.objects.create_user('staff@alpha.com.np', 'Password123!', first_name='Staff')
        self.client_user = User.objects.create_user('client@company.com.np', 'Password123!', first_name='Client')

        # Assign memberships
        FirmMembership.objects.create(user=self.owner, firm=self.firm, role=FirmRole.OWNER)
        FirmMembership.objects.create(user=self.admin, firm=self.firm, role=FirmRole.ADMIN)
        FirmMembership.objects.create(user=self.ca, firm=self.firm, role=FirmRole.CA)
        FirmMembership.objects.create(user=self.senior, firm=self.firm, role=FirmRole.SENIOR)
        FirmMembership.objects.create(user=self.accountant, firm=self.firm, role=FirmRole.ACCOUNTANT)
        FirmMembership.objects.create(user=self.staff, firm=self.firm, role=FirmRole.STAFF)
        FirmMembership.objects.create(user=self.client_user, firm=self.firm, role=FirmRole.CLIENT)

    def test_owner_permissions(self):
        """OWNER has full practice permissions."""
        self.assertTrue(has_firm_permission(self.owner, self.firm, 'manage_settings'))
        self.assertTrue(has_firm_permission(self.owner, self.firm, 'manage_team'))
        self.assertTrue(has_firm_permission(self.owner, self.firm, 'view_audit_logs'))
        self.assertTrue(has_firm_permission(self.owner, self.firm, 'delete_client'))
        self.assertTrue(has_firm_permission(self.owner, self.firm, 'manage_billing'))

    def test_admin_permissions(self):
        """ADMIN has settings and team management permissions."""
        self.assertTrue(has_firm_permission(self.admin, self.firm, 'manage_settings'))
        self.assertTrue(has_firm_permission(self.admin, self.firm, 'manage_team'))
        self.assertTrue(has_firm_permission(self.admin, self.firm, 'invite_team'))
        self.assertTrue(has_firm_permission(self.admin, self.firm, 'view_audit_logs'))

    def test_ca_permissions(self):
        """CA has client, task, document, compliance access, but NOT settings or team management."""
        self.assertTrue(has_firm_permission(self.ca, self.firm, 'view_client'))
        self.assertTrue(has_firm_permission(self.ca, self.firm, 'create_client'))
        self.assertTrue(has_firm_permission(self.ca, self.firm, 'manage_compliance'))
        self.assertTrue(has_firm_permission(self.ca, self.firm, 'view_team'))
        # Restricted areas
        self.assertFalse(has_firm_permission(self.ca, self.firm, 'manage_settings'))
        self.assertFalse(has_firm_permission(self.ca, self.firm, 'manage_team'))
        self.assertFalse(has_firm_permission(self.ca, self.firm, 'view_audit_logs'))

    def test_staff_permissions(self):
        """STAFF has limited operational access only."""
        self.assertTrue(has_firm_permission(self.staff, self.firm, 'view_client'))
        self.assertTrue(has_firm_permission(self.staff, self.firm, 'view_task'))
        self.assertTrue(has_firm_permission(self.staff, self.firm, 'upload_document'))
        # Restricted areas
        self.assertFalse(has_firm_permission(self.staff, self.firm, 'create_client'))
        self.assertFalse(has_firm_permission(self.staff, self.firm, 'manage_settings'))
        self.assertFalse(has_firm_permission(self.staff, self.firm, 'manage_team'))
        self.assertFalse(has_firm_permission(self.staff, self.firm, 'view_billing'))
        self.assertFalse(has_firm_permission(self.staff, self.firm, 'view_reports'))

    def test_client_restrictions(self):
        """CLIENT users are denied internal firm operational access."""
        self.assertFalse(has_firm_permission(self.client_user, self.firm, 'view_client'))
        self.assertFalse(has_firm_permission(self.client_user, self.firm, 'view_team'))
        self.assertFalse(has_firm_permission(self.client_user, self.firm, 'manage_settings'))
        self.assertFalse(has_firm_permission(self.client_user, self.firm, 'view_audit_logs'))
        self.assertEqual(len(get_user_firm_permissions(self.client_user, self.firm)), 0)


class MultiTenancyAndIDORIsolationTests(TestCase):
    """
    Validates complete multi-tenant partition isolation between Firm A and Firm B:
    - URL parameter manipulation
    - POST body manipulation
    - Cross-tenant object ID manipulation
    - Cross-tenant workspace switching
    """
    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()

        # Firm A (Kathmandu practice)
        self.firm_a = Firm.objects.create(name='Firm A & Associates', slug='firm-a', city='Kathmandu')
        self.owner_a = User.objects.create_user('owner_a@firma.com.np', 'PasswordA123!', first_name='OwnerA')
        self.staff_a = User.objects.create_user('staff_a@firma.com.np', 'PasswordA123!', first_name='StaffA')
        self.membership_a_owner = FirmMembership.objects.create(user=self.owner_a, firm=self.firm_a, role=FirmRole.OWNER)
        self.membership_a_staff = FirmMembership.objects.create(user=self.staff_a, firm=self.firm_a, role=FirmRole.STAFF)

        # Firm B (Pokhara practice)
        self.firm_b = Firm.objects.create(name='Firm B & Partners', slug='firm-b', city='Pokhara')
        self.owner_b = User.objects.create_user('owner_b@firmb.com.np', 'PasswordB123!', first_name='OwnerB')
        self.staff_b = User.objects.create_user('staff_b@firmb.com.np', 'PasswordB123!', first_name='StaffB')
        self.membership_b_owner = FirmMembership.objects.create(user=self.owner_b, firm=self.firm_b, role=FirmRole.OWNER)
        self.membership_b_staff = FirmMembership.objects.create(user=self.staff_b, firm=self.firm_b, role=FirmRole.STAFF)

        # Log in User A
        self.client_a.login(email='owner_a@firma.com.np', password='PasswordA123!')
        session_a = self.client_a.session
        session_a['active_firm_id'] = str(self.firm_a.id)
        session_a.save()

        # Log in User B
        self.client_b.login(email='owner_b@firmb.com.np', password='PasswordB123!')
        session_b = self.client_b.session
        session_b['active_firm_id'] = str(self.firm_b.id)
        session_b.save()

    def test_firm_a_cannot_see_firm_b_team(self):
        """Firm A user visiting team page only sees Firm A members, never Firm B members."""
        response = self.client_a.get(reverse('firms:team_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OwnerA')
        self.assertContains(response, 'StaffA')
        self.assertNotContains(response, 'OwnerB')
        self.assertNotContains(response, 'StaffB')

    def test_firm_b_cannot_see_firm_a_team(self):
        """Firm B user visiting team page only sees Firm B members, never Firm A members."""
        response = self.client_b.get(reverse('firms:team_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'OwnerB')
        self.assertContains(response, 'StaffB')
        self.assertNotContains(response, 'OwnerA')
        self.assertNotContains(response, 'StaffA')

    def test_idor_post_manipulation_change_role_rejected(self):
        """
        Firm A user sending a POST to change role of a Firm B member
        receives 404 Not Found (scoped strictly to current firm).
        """
        change_url = reverse('firms:team_change_role', kwargs={'membership_id': self.membership_b_staff.id})
        response = self.client_a.post(change_url, {'role': FirmRole.CA})
        self.assertEqual(response.status_code, 404)

        # Verify Firm B staff role was not altered
        self.membership_b_staff.refresh_from_db()
        self.assertEqual(self.membership_b_staff.role, FirmRole.STAFF)

    def test_idor_post_manipulation_deactivate_member_rejected(self):
        """
        Firm A user attempting to deactivate a Firm B member
        receives 404 Not Found.
        """
        deact_url = reverse('firms:team_deactivate', kwargs={'membership_id': self.membership_b_staff.id})
        response = self.client_a.post(deact_url)
        self.assertEqual(response.status_code, 404)

        # Verify Firm B staff remains ACTIVE
        self.membership_b_staff.refresh_from_db()
        self.assertEqual(self.membership_b_staff.status, MembershipStatus.ACTIVE)

    def test_idor_revoke_invite_cross_tenant_rejected(self):
        """
        Firm A user attempting to revoke an invitation belonging to Firm B
        receives 404 Not Found.
        """
        invitation_b = FirmInvitation.objects.create(
            firm=self.firm_b,
            email='newassociate@firmb.com.np',
            role=FirmRole.SENIOR,
            token='secret-token-b-12345',
            invited_by=self.owner_b,
            expires_at=self.firm_b.created_at,
        )
        revoke_url = reverse('firms:team_revoke_invite', kwargs={'invitation_id': invitation_b.id})
        response = self.client_a.post(revoke_url)
        self.assertEqual(response.status_code, 404)

        # Verify invitation still exists
        self.assertTrue(FirmInvitation.objects.filter(id=invitation_b.id).exists())

    def test_unauthorized_firm_switching_rejected_with_403(self):
        """
        Firm A user attempting to switch active workspace to Firm B
        is rejected with 403 Forbidden.
        """
        switch_url = reverse('firms:switch_firm', kwargs={'firm_id': self.firm_b.id})
        response = self.client_a.post(switch_url)
        self.assertEqual(response.status_code, 403)

        # Session remains Firm A
        self.assertEqual(self.client_a.session.get('active_firm_id'), str(self.firm_a.id))

    def test_authorized_multi_firm_switching_succeeds(self):
        """
        A user who belongs to both Firm A and Firm B can switch workspaces cleanly.
        """
        # Add Owner A as CA in Firm B as well
        FirmMembership.objects.create(user=self.owner_a, firm=self.firm_b, role=FirmRole.CA)

        switch_url = reverse('firms:switch_firm', kwargs={'firm_id': self.firm_b.id})
        response = self.client_a.post(switch_url)
        self.assertRedirects(response, reverse('core:dashboard'))
        self.assertEqual(self.client_a.session.get('active_firm_id'), str(self.firm_b.id))

    def test_get_firm_object_or_404_helper(self):
        """Helper correctly raises Http404 when object belongs to another firm."""
        client_in_firm_b = ClientEntity.objects.create(firm=self.firm_b, name='Pokhara Solar Ltd', pan_number='600112233')

        # Calling with firm_a must raise Http404
        with self.assertRaises(Http404):
            get_firm_object_or_404(ClientEntity, self.firm_a, id=client_in_firm_b.id)

        # Calling with firm_b must succeed
        obj = get_firm_object_or_404(ClientEntity, self.firm_b, id=client_in_firm_b.id)
        self.assertEqual(obj.name, 'Pokhara Solar Ltd')

    def test_staff_cannot_access_firm_settings(self):
        """Staff without manage_settings permission is denied access to firm settings with 403."""
        client_staff = Client()
        client_staff.login(email='staff_a@firma.com.np', password='PasswordA123!')
        session = client_staff.session
        session['active_firm_id'] = str(self.firm_a.id)
        session.save()

        response = client_staff.get(reverse('firms:firm_settings'))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_invite_team_members(self):
        """Staff without invite_team permission cannot send invitations."""
        client_staff = Client()
        client_staff.login(email='staff_a@firma.com.np', password='PasswordA123!')
        session = client_staff.session
        session['active_firm_id'] = str(self.firm_a.id)
        session.save()

        response = client_staff.post(reverse('firms:team_invite'), {
            'email': 'unauthorized@invite.com',
            'role': FirmRole.STAFF,
        })
        self.assertEqual(response.status_code, 403)


class FirmAuthorizationAndPilotSecurityTests(TestCase):
    """
    Dedicated tests verifying all requirements for real pilot deployment:
    - Valid membership resolution & session persistence
    - Invalid membership redirection (no infinite redirect loop)
    - Inactive membership and inactive firm handling
    - Cross-firm IDOR defense for clients, tasks, and checklists
    - Cross-firm task assignment defense
    - Role restrictions (STAFF, ACCOUNTANT, CA, CLIENT)
    - Open redirect defense (LoginView and SwitchFirmView)
    - Session handling & logout session flushing
    """
    def setUp(self):
        self.http_client = Client()

        # Create Firm Alpha (Primary Pilot Practice)
        self.firm_alpha = Firm.objects.create(name='Alpha Advisory Practice', slug='alpha-advisory', city='Kathmandu')

        # Create Firm Beta (Foreign Practice for IDOR Testing)
        self.firm_beta = Firm.objects.create(name='Beta Audit Corp', slug='beta-audit', city='Lalitpur')

        # Users for Alpha
        self.alpha_owner = User.objects.create_user('alpha_owner@alpha.com', 'Pass12345!', first_name='AlphaOwner')
        self.alpha_ca = User.objects.create_user('alpha_ca@alpha.com', 'Pass12345!', first_name='AlphaCA')
        self.alpha_accountant = User.objects.create_user('alpha_acc@alpha.com', 'Pass12345!', first_name='AlphaAcc')
        self.alpha_staff = User.objects.create_user('alpha_staff@alpha.com', 'Pass12345!', first_name='AlphaStaff')
        self.alpha_client_user = User.objects.create_user('client_user@portal.com', 'Pass12345!', first_name='ClientUser')

        # Memberships for Alpha
        FirmMembership.objects.create(user=self.alpha_owner, firm=self.firm_alpha, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.alpha_ca, firm=self.firm_alpha, role=FirmRole.CA, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.alpha_accountant, firm=self.firm_alpha, role=FirmRole.ACCOUNTANT, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.alpha_staff, firm=self.firm_alpha, role=FirmRole.STAFF, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.alpha_client_user, firm=self.firm_alpha, role=FirmRole.CLIENT, status=MembershipStatus.ACTIVE)

        # User and Membership for Beta
        self.beta_owner = User.objects.create_user('beta_owner@beta.com', 'Pass12345!', first_name='BetaOwner')
        FirmMembership.objects.create(user=self.beta_owner, firm=self.firm_beta, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)

        # Unaffiliated User (No firm memberships at all)
        self.lonely_user = User.objects.create_user('lonely@nowhere.com', 'Pass12345!', first_name='LonelyUser')

        # Alpha entity objects
        self.client_alpha = ClientEntity.objects.create(firm=self.firm_alpha, name='Alpha Client Pvt Ltd', pan_number='111222333')
        self.task_alpha = Task.objects.create(firm=self.firm_alpha, title='Alpha Tax Filing', client=self.client_alpha)
        self.item_alpha = TaskChecklistItem.objects.create(firm=self.firm_alpha, task=self.task_alpha, title='Alpha Collect Form 10')

        # Beta entity objects
        self.client_beta = ClientEntity.objects.create(firm=self.firm_beta, name='Beta Client Corp', pan_number='999888777')
        self.task_beta = Task.objects.create(firm=self.firm_beta, title='Beta Audit Procedure', client=self.client_beta)
        self.item_beta = TaskChecklistItem.objects.create(firm=self.firm_beta, task=self.task_beta, title='Beta Reconcile Bank')

    def test_valid_membership_resolution_and_session_persistence(self):
        """Active firm is resolved, stored in session, and persists across authenticated views."""
        self.http_client.login(email='alpha_owner@alpha.com', password='Pass12345!')

        # Access dashboard
        response = self.http_client.get(reverse('core:dashboard'))
        self.assertEqual(response.status_code, 200)

        # Session should now have active_firm_id
        session_firm_id = self.http_client.session.get('active_firm_id')
        self.assertEqual(session_firm_id, str(self.firm_alpha.id))

        # Core workspace pages must render without errors
        for view_name in [
            'clients:client_list',
            'tasks:task_list',
            'documents:document_list',
            'compliance:compliance_list',
            'calendar_app:calendar_view',
            'messages_app:inbox',
        ]:
            resp = self.http_client.get(reverse(view_name))
            self.assertEqual(resp.status_code, 200, f"Failed on view {view_name}")

    def test_invalid_membership_redirects_to_no_firm_page_without_loop(self):
        """Authenticated user without any firm membership is redirected to no_firm view without looping."""
        self.http_client.login(email='lonely@nowhere.com', password='Pass12345!')

        # Visiting dashboard should redirect to firms:no_firm
        response = self.http_client.get(reverse('core:dashboard'))
        self.assertRedirects(response, reverse('firms:no_firm'))

        # Visiting firms:no_firm directly returns 200 OK (no redirect loop back to register/dashboard)
        no_firm_resp = self.http_client.get(reverse('firms:no_firm'))
        self.assertEqual(no_firm_resp.status_code, 200)
        self.assertContains(no_firm_resp, 'Active Workspace Required')

    def test_inactive_membership_denied(self):
        """User with INACTIVE membership status cannot resolve an active firm and is redirected."""
        inactive_user = User.objects.create_user('inactive@alpha.com', 'Pass12345!', first_name='InactiveUser')
        FirmMembership.objects.create(
            user=inactive_user,
            firm=self.firm_alpha,
            role=FirmRole.STAFF,
            status=MembershipStatus.INACTIVE,
            is_active=False
        )

        self.http_client.login(email='inactive@alpha.com', password='Pass12345!')
        response = self.http_client.get(reverse('core:dashboard'))
        self.assertRedirects(response, reverse('firms:no_firm'))

    def test_inactive_firm_denied(self):
        """User whose firm is marked inactive (is_active=False) cannot access firm workspace."""
        inactive_firm = Firm.objects.create(name='Deactivated Practice', slug='deactivated-slug', is_active=False)
        user_of_inactive_firm = User.objects.create_user('deact_user@domain.com', 'Pass12345!')
        FirmMembership.objects.create(
            user=user_of_inactive_firm,
            firm=inactive_firm,
            role=FirmRole.OWNER,
            status=MembershipStatus.ACTIVE,
            is_active=True
        )

        self.http_client.login(email='deact_user@domain.com', password='Pass12345!')
        response = self.http_client.get(reverse('core:dashboard'))
        self.assertRedirects(response, reverse('firms:no_firm'))

    def test_cross_firm_client_detail_idor_defense(self):
        """Firm Alpha user cannot view Firm Beta client (must 404)."""
        self.http_client.login(email='alpha_owner@alpha.com', password='Pass12345!')

        # HTML detail view
        url = reverse('clients:client_detail', kwargs={'client_id': self.client_beta.id})
        response = self.http_client.get(url)
        self.assertEqual(response.status_code, 404)

        # JSON endpoint
        json_url = reverse('clients:client_detail_json', kwargs={'client_id': self.client_beta.id})
        json_resp = self.http_client.get(json_url)
        self.assertEqual(json_resp.status_code, 404)

    def test_cross_firm_task_detail_and_checklist_idor_defense(self):
        """Firm Alpha user cannot view, edit, or toggle items on Firm Beta task (must 404)."""
        self.http_client.login(email='alpha_owner@alpha.com', password='Pass12345!')

        # Task detail 404
        task_url = reverse('tasks:task_detail', kwargs={'task_id': self.task_beta.id})
        response = self.http_client.get(task_url)
        self.assertEqual(response.status_code, 404)

        # Task edit POST 404
        edit_url = reverse('tasks:task_edit', kwargs={'task_id': self.task_beta.id})
        edit_resp = self.http_client.post(edit_url, {'title': 'Tampered Title', 'priority': 'HIGH'})
        self.assertEqual(edit_resp.status_code, 404)

        # Checklist item toggle 404
        toggle_url = reverse('tasks:task_checklist_toggle', kwargs={'item_id': self.item_beta.id})
        toggle_resp = self.http_client.post(toggle_url)
        self.assertEqual(toggle_resp.status_code, 404)

    def test_cross_firm_task_assignment_defense(self):
        """Firm Alpha user cannot assign a task to a user belonging to Firm Beta."""
        self.http_client.login(email='alpha_owner@alpha.com', password='Pass12345!')

        assign_url = reverse('tasks:task_assign', kwargs={'task_id': self.task_alpha.id})
        # Attempt to assign to beta_owner
        self.http_client.post(assign_url, {'assigned_to': str(self.beta_owner.id)})

        self.task_alpha.refresh_from_db()
        # Assigned to must NOT be beta_owner
        self.assertNotEqual(self.task_alpha.assigned_to, self.beta_owner)

    def test_role_restriction_staff_cannot_create_client(self):
        """Staff without create_client permission receives 403 Forbidden."""
        self.http_client.login(email='alpha_staff@alpha.com', password='Pass12345!')

        # GET form
        resp_get = self.http_client.get(reverse('clients:client_create'))
        self.assertEqual(resp_get.status_code, 403)

        # POST form
        resp_post = self.http_client.post(reverse('clients:client_create'), {
            'name': 'Hacker Corp',
            'client_type': 'CORPORATE',
        })
        self.assertEqual(resp_post.status_code, 403)

    def test_role_restriction_accountant_cannot_delete_client(self):
        """Accountant without delete_client permission receives 403 Forbidden."""
        self.http_client.login(email='alpha_acc@alpha.com', password='Pass12345!')

        url = reverse('clients:client_deactivate', kwargs={'client_id': self.client_alpha.id})
        response = self.http_client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_role_restriction_client_role_cannot_access_practice_dashboard_and_views(self):
        """Client users are strictly forbidden from internal firm views."""
        self.http_client.login(email='client_user@portal.com', password='Pass12345!')

        for view_name in [
            'core:dashboard',
            'tasks:task_list',
            'clients:client_list',
            'calendar_app:calendar_view',
            'messages_app:inbox',
        ]:
            response = self.http_client.get(reverse(view_name))
            self.assertEqual(response.status_code, 403, f"Client user was not blocked on {view_name}")

    def test_open_redirect_protection_login(self):
        """LoginView safely neutralizes untrusted open redirect URLs."""
        # Absolute URL with different host
        resp = self.http_client.post(reverse('accounts:login') + '?next=https://malicious-attacker.com/steal', {
            'email': 'alpha_owner@alpha.com',
            'password': 'Pass12345!',
        })
        self.assertRedirects(resp, reverse('core:dashboard'))

        # Protocol-relative URL
        resp2 = self.http_client.post(reverse('accounts:login') + '?next=//malicious-attacker.com', {
            'email': 'alpha_owner@alpha.com',
            'password': 'Pass12345!',
        })
        self.assertRedirects(resp2, reverse('core:dashboard'))

    def test_open_redirect_protection_switch_firm(self):
        """SwitchFirmView safely neutralizes open redirect query parameters."""
        self.http_client.login(email='alpha_owner@alpha.com', password='Pass12345!')

        switch_url = reverse('firms:switch_firm', kwargs={'firm_id': self.firm_alpha.id}) + '?next=https://malicious.com'
        response = self.http_client.post(switch_url)
        self.assertRedirects(response, reverse('core:dashboard'))

    def test_logout_session_flushing(self):
        """Logout flushes session and clears active firm context."""
        self.http_client.login(email='alpha_owner@alpha.com', password='Pass12345!')
        self.http_client.get(reverse('core:dashboard'))

        # Confirm session has active firm
        self.assertEqual(self.http_client.session.get('active_firm_id'), str(self.firm_alpha.id))

        # Perform logout
        logout_resp = self.http_client.post(reverse('accounts:logout'))
        self.assertRedirects(logout_resp, reverse('core:landing'))

        # active_firm_id should be cleared
        self.assertIsNone(self.http_client.session.get('active_firm_id'))

        # Subsequent dashboard request must redirect to login
        dash_resp = self.http_client.get(reverse('core:dashboard'))
        self.assertEqual(dash_resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), dash_resp['Location'])

