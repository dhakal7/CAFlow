import secrets
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode, url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

from accounts.forms import (
    ChangePasswordForm,
    FirmRegistrationForm,
    ForgotPasswordForm,
    LoginForm,
    ResetPasswordForm,
    UserProfileForm,
)
from accounts.models import User
from audit.services import log_audit
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus


class LoginView(FormView):
    """
    User authentication endpoint.
    Validates credentials, initializes active firm workspace session, and records audit.
    """
    template_name = 'accounts/login.html'
    form_class = LoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if getattr(request, 'firm', None):
                return redirect('core:dashboard')
            return redirect('firms:no_firm')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.cleaned_data['user']
        remember_me = form.cleaned_data.get('remember_me', True)

        login(self.request, user)

        if not remember_me:
            self.request.session.set_expiry(0)
        else:
            self.request.session.set_expiry(settings.SESSION_COOKIE_AGE)

        # Set default active firm if user has one
        membership = FirmMembership.objects.select_related('firm').filter(
            user=user,
            status=MembershipStatus.ACTIVE,
            is_active=True,
            firm__is_active=True,
        ).order_by('joined_at').first()

        if membership:
            self.request.session['active_firm_id'] = str(membership.firm.id)
        else:
            self.request.session.pop('active_firm_id', None)

        log_audit(
            request=self.request,
            firm=membership.firm if membership else None,
            user=user,
            action='LOGIN',
            description=f"User {user.email} signed in successfully",
        )

        messages.success(self.request, _(f"Welcome back, {user.get_short_name()}!"))

        next_url = self.request.GET.get('next') or self.request.POST.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure()
        ):
            return redirect(next_url)

        if not membership:
            return redirect('firms:no_firm')
        return redirect('core:dashboard')


class LogoutView(View):
    """
    Terminates the user's authenticated session securely.
    Supports both POST and GET dispatch while completely flushing the session.
    """
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            log_audit(
                request=request,
                user=request.user,
                action='LOGOUT',
                description=f"User {request.user.email} signed out",
            )
            logout(request)
            request.session.flush()
            messages.info(request, _("You have been signed out successfully."))
        return redirect('core:landing')


class RegisterView(FormView):
    """
    New Firm practice owner onboarding flow.
    Creates User, Firm, and OWNER Membership atomically.
    """
    template_name = 'accounts/register.html'
    form_class = FirmRegistrationForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if getattr(request, 'firm', None):
                return redirect('core:dashboard')
            return redirect('firms:no_firm')
        return super().dispatch(request, *args, **kwargs)


    def form_valid(self, form):
        data = form.cleaned_data

        with transaction.atomic():
            # 1. Create User
            verification_token = secrets.token_urlsafe(32)
            user = User.objects.create_user(
                email=data['email'],
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                phone=data.get('phone', ''),
                is_active=True,
                is_email_verified=False,
                email_verification_token=verification_token,
            )

            # 2. Create Firm
            firm = Firm.objects.create(
                name=data['firm_name'],
                email=data['email'],
                phone=data.get('phone', ''),
                pan_number=data.get('pan_number', ''),
                city=data.get('city') or 'Kathmandu',
                address=data.get('address', ''),
                country='Nepal',
                timezone='Asia/Kathmandu',
                currency='NPR',
            )

            # 3. Create OWNER FirmMembership
            membership = FirmMembership.objects.create(
                user=user,
                firm=firm,
                role=FirmRole.OWNER,
                status=MembershipStatus.ACTIVE,
                is_primary_contact=True,
            )

            # Associate legacy field
            user.firm = firm
            user.save(update_fields=['firm'])

        # Establish active session
        login(self.request, user)
        self.request.session['active_firm_id'] = str(firm.id)

        # Log audit trail
        log_audit(
            request=self.request,
            firm=firm,
            user=user,
            action='REGISTER',
            object_type='Firm',
            object_id=str(firm.id),
            description=f"Registered firm {firm.name} with Owner {user.email}",
        )

        # Send email verification
        verify_url = self.request.build_absolute_uri(f"/verify-email/{verification_token}/")
        try:
            send_mail(
                subject=f"Verify your email for CAFlow — {firm.name}",
                message=f"Namaste {user.first_name},\n\nThank you for creating your practice workspace on CAFlow.\n\nPlease verify your email by clicking the link below:\n{verify_url}\n\nWarm regards,\nCAFlow Team",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass

        messages.success(
            self.request,
            _(f"Welcome to CAFlow, {user.first_name}! Your practice workspace '{firm.name}' has been created.")
        )
        return redirect('core:dashboard')


class ForgotPasswordView(FormView):
    """
    Password reset request endpoint.
    Prevents account enumeration by displaying an identical confirmation regardless of email existence.
    """
    template_name = 'accounts/forgot_password.html'
    form_class = ForgotPasswordForm

    def form_valid(self, form):
        email = form.cleaned_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            token = default_token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = self.request.build_absolute_uri(
                reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})
            )

            log_audit(
                request=self.request,
                user=user,
                action='PASSWORD_RESET_REQ',
                description=f"Password reset link requested for {email}",
            )

            try:
                send_mail(
                    subject="Reset your CAFlow account password",
                    message=f"Namaste {user.get_short_name()},\n\nA password reset was requested for your CAFlow account.\n\nClick here to reset your password:\n{reset_url}\n\nIf you did not request this, you can safely ignore this email.\n\nCAFlow Security Team",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:
                pass

        # Always show success state to prevent email enumeration
        return render(self.request, 'accounts/forgot_password_sent.html', {'email': email})


class ResetPasswordConfirmView(FormView):
    """
    Sets a new password using the validated cryptographic reset token.
    """
    template_name = 'accounts/reset_password.html'
    form_class = ResetPasswordForm

    def get_user(self):
        try:
            uid = force_str(urlsafe_base64_decode(self.kwargs.get('uidb64', '')))
            return User.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None

    def dispatch(self, request, *args, **kwargs):
        user = self.get_user()
        token = self.kwargs.get('token', '')

        if not user or not default_token_generator.check_token(user, token):
            messages.error(request, _("This password reset link is invalid or has expired."))
            return render(request, 'accounts/reset_password_invalid.html')

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = self.get_user()
        new_password = form.cleaned_data['new_password']
        user.set_password(new_password)
        user.save()

        log_audit(
            request=self.request,
            user=user,
            action='PASSWORD_RESET',
            description=f"Password reset successfully completed for {user.email}",
        )

        messages.success(self.request, _("Your password has been successfully reset. You may now sign in."))
        return redirect('accounts:password_reset_done')


class PasswordResetDoneView(TemplateView):
    template_name = 'accounts/reset_password_done.html'


class VerifyEmailView(View):
    """
    Validates user email verification token and marks account as verified.
    """
    def get(self, request, token):
        user = User.objects.filter(email_verification_token=token).first()

        if not user or not token:
            return render(request, 'accounts/verify_email.html', {
                'success': False,
                'message': _("This email verification link is invalid or has already been used.")
            })

        user.is_email_verified = True
        user.email_verification_token = ''
        user.save(update_fields=['is_email_verified', 'email_verification_token'])

        log_audit(
            request=request,
            user=user,
            action='EMAIL_VERIFIED',
            description=f"Email verified for {user.email}",
        )

        return render(request, 'accounts/verify_email.html', {
            'success': True,
            'user': user,
            'message': _("Your email has been successfully verified! Your practice account is fully activated.")
        })


class ResendVerificationEmailView(LoginRequiredMixin, View):
    """Allows authenticated user to trigger a fresh verification email."""
    def post(self, request):
        user = request.user
        if user.is_email_verified:
            messages.info(request, _("Your email address is already verified."))
            return redirect('accounts:profile')

        user.email_verification_token = secrets.token_urlsafe(32)
        user.save(update_fields=['email_verification_token'])

        verify_url = request.build_absolute_uri(f"/verify-email/{user.email_verification_token}/")
        try:
            send_mail(
                subject="Verify your CAFlow Practice Account",
                message=f"Namaste {user.get_short_name()},\n\nPlease verify your email by clicking the link below:\n{verify_url}\n\nWarm regards,\nCAFlow Team",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception:
            pass

        messages.success(request, _(f"A new verification link has been sent to {user.email}."))
        return redirect('accounts:profile')


class ProfileView(LoginRequiredMixin, View):
    """
    User Profile view: displays personal accreditation, active firm roles,
    and handles profile updates and password changes.
    """
    template_name = 'accounts/profile.html'

    def get(self, request):
        user = request.user
        profile_form = UserProfileForm(instance=user)
        password_form = ChangePasswordForm(user=user)

        memberships = FirmMembership.objects.select_related('firm').filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        )

        return render(request, self.template_name, {
            'user': user,
            'profile_form': profile_form,
            'password_form': password_form,
            'memberships': memberships,
            'breadcrumbs': [
                {'title': 'Practice Account', 'url': ''},
                {'title': 'Profile & Credentials', 'url': ''},
            ],
        })

    def post(self, request):
        user = request.user
        action = request.POST.get('action', 'update_profile')

        if action == 'update_profile':
            profile_form = UserProfileForm(request.POST, request.FILES, instance=user)
            password_form = ChangePasswordForm(user=user)

            if profile_form.is_valid():
                profile_form.save()
                log_audit(
                    request=request,
                    user=user,
                    action='PROFILE_UPDATE',
                    description=f"User {user.email} updated their profile info",
                )
                messages.success(request, _("Your profile credentials have been successfully updated."))
                return redirect('accounts:profile')

        elif action == 'change_password':
            password_form = ChangePasswordForm(user, request.POST)
            profile_form = UserProfileForm(instance=user)

            if password_form.is_valid():
                new_pass = password_form.cleaned_data['new_password']
                user.set_password(new_pass)
                user.save()
                update_session_auth_hash(request, user)

                log_audit(
                    request=request,
                    user=user,
                    action='PASSWORD_CHANGE',
                    description=f"User {user.email} changed their password",
                )
                messages.success(request, _("Your password has been changed successfully."))
                return redirect('accounts:profile')

        memberships = FirmMembership.objects.select_related('firm').filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        )

        return render(request, self.template_name, {
            'user': user,
            'profile_form': profile_form,
            'password_form': password_form,
            'memberships': memberships,
            'breadcrumbs': [
                {'title': 'Practice Account', 'url': ''},
                {'title': 'Profile & Credentials', 'url': ''},
            ],
        })
