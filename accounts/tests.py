import secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from audit.models import AuditLog
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus

User = get_user_model()


class AuthenticationAndUserTests(TestCase):
    """
    Validates complete authentication lifecycle:
    Registration, Login, Logout, Password Reset, Email Verification, and Profile.
    """
    def setUp(self):
        self.client = Client()

    def test_custom_user_model_fields_and_creation(self):
        """User model adheres to custom architecture with email as unique identifier."""
        user = User.objects.create_user(
            email='partner@firm.com.np',
            password='TestPassword123!',
            first_name='Suyog',
            last_name='Dhakal',
            phone='+977 9851000000',
        )
        self.assertEqual(user.email, 'partner@firm.com.np')
        self.assertEqual(user.first_name, 'Suyog')
        self.assertEqual(user.last_name, 'Dhakal')
        self.assertEqual(user.phone, '+977 9851000000')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.get_full_name(), 'Suyog Dhakal')
        self.assertEqual(user.get_short_name(), 'Suyog')

    def test_registration_creates_owner_firm_and_membership(self):
        """New practice owner registration creates User, Firm, and OWNER membership atomically."""
        post_data = {
            'first_name': 'Ram',
            'last_name': 'Khadka',
            'email': 'ram@khadkaca.com.np',
            'password': 'StrongPassword2081!',
            'password_confirm': 'StrongPassword2081!',
            'firm_name': 'Khadka & Associates, Chartered Accountants',
            'phone': '+977 9841234567',
            'pan_number': '300998877',
            'city': 'Kathmandu',
            'address': 'New Road',
            'terms_accepted': 'on',
        }
        response = self.client.post(reverse('accounts:register'), post_data)
        self.assertRedirects(response, reverse('core:dashboard'))

        # Check User created
        user = User.objects.get(email='ram@khadkaca.com.np')
        self.assertEqual(user.first_name, 'Ram')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertTrue(len(user.email_verification_token) > 0)

        # Check Firm created
        firm = Firm.objects.get(name='Khadka & Associates, Chartered Accountants')
        self.assertEqual(firm.pan_number, '300998877')

        # Check OWNER Membership
        membership = FirmMembership.objects.get(user=user, firm=firm)
        self.assertEqual(membership.role, FirmRole.OWNER)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)

        # Check Active Firm set in session
        self.assertEqual(self.client.session.get('active_firm_id'), str(firm.id))

        # Check AuditLog entry created
        audit_entry = AuditLog.objects.filter(user=user, action='REGISTER').first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.firm, firm)

    def test_registration_password_mismatch(self):
        """Registration rejects mismatched passwords."""
        post_data = {
            'first_name': 'Ram',
            'last_name': 'Khadka',
            'email': 'ram@khadkaca.com.np',
            'password': 'StrongPassword2081!',
            'password_confirm': 'DifferentPassword2081!',
            'firm_name': 'Khadka & Associates',
            'terms_accepted': 'on',
        }
        response = self.client.post(reverse('accounts:register'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'password_confirm', 'Passwords do not match.')

    def test_login_flow(self):
        """User can log in with valid credentials, session initializes active firm."""
        user = User.objects.create_user(email='ca@firm.com.np', password='ValidPassword123!')
        firm = Firm.objects.create(name='Valid Firm', slug='valid-firm')
        FirmMembership.objects.create(user=user, firm=firm, role=FirmRole.CA, status=MembershipStatus.ACTIVE)

        # Valid credentials
        response = self.client.post(reverse('accounts:login'), {
            'email': 'ca@firm.com.np',
            'password': 'ValidPassword123!',
            'remember_me': 'on',
        })
        self.assertRedirects(response, reverse('core:dashboard'))
        self.assertEqual(self.client.session.get('active_firm_id'), str(firm.id))

        # AuditLog recorded
        audit = AuditLog.objects.filter(user=user, action='LOGIN').first()
        self.assertIsNotNone(audit)

    def test_login_invalid_credentials(self):
        """Invalid credentials display error alert."""
        User.objects.create_user(email='ca@firm.com.np', password='ValidPassword123!')
        response = self.client.post(reverse('accounts:login'), {
            'email': 'ca@firm.com.np',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email or password")

    def test_inactive_user_cannot_login(self):
        """Inactive accounts cannot sign in."""
        User.objects.create_user(email='inactive@firm.com.np', password='ValidPassword123!', is_active=False)
        response = self.client.post(reverse('accounts:login'), {
            'email': 'inactive@firm.com.np',
            'password': 'ValidPassword123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "deactivated")

    def test_logout_terminates_session(self):
        """Logout flushes authenticated session and records audit."""
        user = User.objects.create_user(email='ca@firm.com.np', password='ValidPassword123!')
        self.client.login(email='ca@firm.com.np', password='ValidPassword123!')

        response = self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('core:landing'))

        # Verify session flushed
        self.assertNotIn('_auth_user_id', self.client.session)

        # AuditLog recorded
        audit = AuditLog.objects.filter(user=user, action='LOGOUT').first()
        self.assertIsNotNone(audit)

    def test_password_reset_flow(self):
        """Password reset uses secure tokens and avoids email enumeration."""
        user = User.objects.create_user(email='resetme@firm.com.np', password='OldPassword123!')

        # 1. Request reset
        response = self.client.post(reverse('accounts:password_reset'), {'email': 'resetme@firm.com.np'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check Your Email")

        # Nonexistent email displays identical neutral message
        response2 = self.client.post(reverse('accounts:password_reset'), {'email': 'nonexistent@firm.com.np'})
        self.assertEqual(response2.status_code, 200)
        self.assertContains(response2, "Check Your Email")

        # 2. Reset token confirmation
        token = default_token_generator.make_token(user)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        confirm_url = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})

        get_res = self.client.get(confirm_url)
        self.assertEqual(get_res.status_code, 200)

        # 3. Submit new password
        post_res = self.client.post(confirm_url, {
            'new_password': 'BrandNewPassword2081!',
            'new_password_confirm': 'BrandNewPassword2081!',
        })
        self.assertRedirects(post_res, reverse('accounts:password_reset_done'))

        # Verify new password works
        user.refresh_from_db()
        self.assertTrue(user.check_password('BrandNewPassword2081!'))

    def test_email_verification_flow(self):
        """User email verification token activates verification status."""
        token = secrets.token_urlsafe(32)
        user = User.objects.create_user(
            email='verify@firm.com.np',
            password='Password123!',
            is_email_verified=False,
            email_verification_token=token,
        )

        verify_url = reverse('accounts:verify_email', kwargs={'token': token})
        response = self.client.get(verify_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email Verified!")

        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertEqual(user.email_verification_token, '')

        # Invalid token fails cleanly
        bad_response = self.client.get(reverse('accounts:verify_email', kwargs={'token': 'invalid-token-123'}))
        self.assertEqual(bad_response.status_code, 200)
        self.assertContains(bad_response, "Verification Link Invalid")

    def test_user_profile_edit(self):
        """Authenticated user can update profile details."""
        user = User.objects.create_user(
            email='editprofile@firm.com.np',
            password='Password123!',
            first_name='Original',
            last_name='Name',
        )
        self.client.login(email='editprofile@firm.com.np', password='Password123!')

        response = self.client.post(reverse('accounts:profile'), {
            'action': 'update_profile',
            'first_name': 'UpdatedFirst',
            'last_name': 'UpdatedLast',
            'phone': '+977 9811223344',
            'ican_membership_no': 'ICAN-FCA-9988',
        })
        self.assertRedirects(response, reverse('accounts:profile'))

        user.refresh_from_db()
        self.assertEqual(user.first_name, 'UpdatedFirst')
        self.assertEqual(user.last_name, 'UpdatedLast')
        self.assertEqual(user.phone, '+977 9811223344')
        self.assertEqual(user.ican_membership_no, 'ICAN-FCA-9988')
