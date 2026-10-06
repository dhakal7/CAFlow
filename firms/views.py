from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from accounts.models import User
from audit.services import log_audit
from firms.forms import (
    AcceptInvitationRegistrationForm,
    ChangeMemberRoleForm,
    FirmCreateForm,
    FirmSettingsForm,
    InviteStaffForm,
)
from firms.mixins import FirmRequiredMixin, PermissionRequiredMixin, RoleRequiredMixin
from firms.models import Firm, FirmInvitation, FirmMembership, FirmRole, MembershipStatus
from firms.services import (
    accept_firm_invitation,
    create_firm_invitation,
    get_firm_object_or_404,
    switch_active_firm,
)


class NoFirmView(LoginRequiredMixin, View):
    """
    Renders an informative empty/recovery state when an authenticated user
    does not currently belong to an active firm workspace.
    Displays pending invitations and actions to register a practice or sign out.
    Neutralizes infinite redirect loops.
    """
    template_name = 'firms/no_firm.html'

    def get(self, request):
        if getattr(request, 'firm', None):
            return redirect('core:dashboard')

        # Check for pending invitations sent to this user's email
        pending_invites = FirmInvitation.objects.select_related('firm', 'invited_by').filter(
            email__iexact=request.user.email,
            is_accepted=False,
        ).order_by('-created_at')

        # Check for inactive or suspended memberships
        other_memberships = FirmMembership.objects.select_related('firm').filter(
            user=request.user,
        ).exclude(
            status=MembershipStatus.ACTIVE,
            firm__is_active=True,
            is_active=True,
        )

        create_form = FirmCreateForm()

        return render(request, self.template_name, {
            'pending_invites': pending_invites,
            'other_memberships': other_memberships,
            'create_form': create_form,
        })


class FirmCreateView(LoginRequiredMixin, View):
    """
    Allows an authenticated user without an active firm to establish a new firm practice workspace.
    Creates Firm, assigns user as OWNER, activates workspace session.
    """
    template_name = 'firms/firm_create.html'

    def get(self, request):
        form = FirmCreateForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = FirmCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                firm = form.save()
                membership = FirmMembership.objects.create(
                    firm=firm,
                    user=request.user,
                    role=FirmRole.OWNER,
                    status=MembershipStatus.ACTIVE,
                    is_primary_contact=True,
                )
                request.user.firm = firm
                request.user.save(update_fields=['firm'])

            request.session['active_firm_id'] = str(firm.id)
            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='CREATE',
                object_type='Firm',
                object_id=str(firm.id),
                description=f"User {request.user.email} created practice workspace {firm.name}",
            )
            messages.success(request, _(f"Practice workspace '{firm.name}' successfully created!"))
            return redirect('core:dashboard')

        return render(request, self.template_name, {'form': form})


class FirmSettingsView(PermissionRequiredMixin, View):
    """
    Firm preferences and organizational settings.
    Restricted to OWNER and ADMIN roles (manage_settings permission).
    """
    firm_permission = 'manage_settings'
    template_name = 'firms/settings.html'

    def get(self, request):
        firm = request.firm
        form = FirmSettingsForm(instance=firm)
        return render(request, self.template_name, {
            'firm': firm,
            'form': form,
            'breadcrumbs': [
                {'title': 'Practice Management', 'url': ''},
                {'title': 'Firm Settings', 'url': ''},
            ],
        })

    def post(self, request):
        firm = request.firm
        form = FirmSettingsForm(request.POST, request.FILES, instance=firm)

        if form.is_valid():
            form.save()
            log_audit(
                request=request,
                firm=firm,
                user=request.user,
                action='FIRM_UPDATE',
                object_type='Firm',
                object_id=str(firm.id),
                description=f"Updated settings for {firm.name}",
            )
            messages.success(request, _("Firm settings and preferences successfully updated."))
            return redirect('firms:firm_settings')

        return render(request, self.template_name, {
            'firm': firm,
            'form': form,
            'breadcrumbs': [
                {'title': 'Practice Management', 'url': ''},
                {'title': 'Firm Settings', 'url': ''},
            ],
        })


class SwitchFirmView(LoginRequiredMixin, View):

    """
    Switches the active workspace to another firm that the user belongs to.
    Rejects any firm where the user does not have active membership with 403 Forbidden.
    """
    def post(self, request, firm_id):
        try:
            firm = switch_active_firm(request, firm_id)
            messages.success(request, _(f"Switched active workspace to {firm.name}."))
        except PermissionDenied as e:
            messages.error(request, str(e))
            return HttpResponseForbidden("Forbidden: Cross-tenant workspace access denied.")

        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect('core:dashboard')

    def get(self, request, firm_id):
        return self.post(request, firm_id)



class TeamListView(PermissionRequiredMixin, View):
    """
    Renders practice team roster and pending invitations.
    Requires view_team permission.
    """
    firm_permission = 'view_team'
    template_name = 'firms/team_list.html'

    def get(self, request):
        firm = request.firm
        memberships = FirmMembership.objects.select_related('user').filter(
            firm=firm
        ).order_by('role', '-joined_at')

        invitations = FirmInvitation.objects.filter(
            firm=firm,
            is_accepted=False,
        ).order_by('-created_at')

        invite_form = InviteStaffForm()
        can_invite = request.has_firm_perm('invite_team')
        can_manage = request.has_firm_perm('manage_team')

        return render(request, self.template_name, {
            'firm': firm,
            'memberships': memberships,
            'invitations': invitations,
            'invite_form': invite_form,
            'can_invite': can_invite,
            'can_manage': can_manage,
            'role_choices': [c for c in FirmRole.choices if c[0] != FirmRole.OWNER],
            'breadcrumbs': [
                {'title': 'Practice Management', 'url': ''},
                {'title': 'Team & Staff', 'url': ''},
            ],
        })


class TeamInviteView(PermissionRequiredMixin, View):
    """
    Dispatches invitation to a new team member.
    Requires invite_team permission.
    """
    firm_permission = 'invite_team'

    def post(self, request):
        form = InviteStaffForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            try:
                invitation = create_firm_invitation(
                    request=request,
                    firm=request.firm,
                    email=email,
                    role=role,
                    invited_by=request.user,
                )
                messages.success(
                    request,
                    _(f"Invitation successfully sent to {email} as {invitation.get_role_display()}.")
                )
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, _("Please provide a valid email and role."))

        return redirect('firms:team_list')


class TeamChangeRoleView(PermissionRequiredMixin, View):
    """
    Modifies an existing member's role within the active firm.
    Strictly scoped to the active firm to prevent IDOR attacks.
    """
    firm_permission = 'manage_team'

    def post(self, request, membership_id):
        # Prevent IDOR by scoping lookup strictly to request.firm
        membership = get_firm_object_or_404(FirmMembership, request.firm, id=membership_id)

        # Cannot modify OWNER role unless current user is OWNER
        if membership.role == FirmRole.OWNER and request.firm_membership.role != FirmRole.OWNER:
            raise PermissionDenied(_("Only the firm owner can modify practice leadership."))

        # Prevent changing own role if that removes manage_team permission
        if membership.user_id == request.user.id and request.firm_membership.role == FirmRole.OWNER:
            messages.error(request, _("The primary Firm Owner cannot change their own leadership role."))
            return redirect('firms:team_list')

        new_role = request.POST.get('role')
        if new_role in dict(FirmRole.choices) and new_role != FirmRole.OWNER:
            old_role = membership.get_role_display()
            membership.role = new_role
            membership.save(update_fields=['role'])

            log_audit(
                request=request,
                firm=request.firm,
                user=request.user,
                action='ROLE_CHANGE',
                object_type='FirmMembership',
                object_id=str(membership.id),
                description=f"Changed {membership.user.email} role from {old_role} to {membership.get_role_display()}",
            )
            messages.success(request, _(f"Updated role for {membership.user.get_full_name()} to {membership.get_role_display()}."))
        else:
            messages.error(request, _("Invalid role selection."))

        return redirect('firms:team_list')


class TeamDeactivateMemberView(PermissionRequiredMixin, View):
    """
    Deactivates a team member from the firm.
    Strictly scoped to active firm to prevent cross-tenant manipulation.
    """
    firm_permission = 'manage_team'

    def post(self, request, membership_id):
        membership = get_firm_object_or_404(FirmMembership, request.firm, id=membership_id)

        if membership.role == FirmRole.OWNER:
            messages.error(request, _("The Firm Owner cannot be deactivated."))
            return redirect('firms:team_list')

        if membership.user_id == request.user.id:
            messages.error(request, _("You cannot deactivate your own membership."))
            return redirect('firms:team_list')

        membership.status = MembershipStatus.INACTIVE
        membership.save(update_fields=['status'])

        log_audit(
            request=request,
            firm=request.firm,
            user=request.user,
            action='MEMBER_DEACTIVATED',
            object_type='FirmMembership',
            object_id=str(membership.id),
            description=f"Deactivated team member {membership.user.email}",
        )
        messages.success(request, _(f"{membership.user.get_full_name()} has been deactivated from {request.firm.name}."))
        return redirect('firms:team_list')


class TeamReactivateMemberView(PermissionRequiredMixin, View):
    """
    Reactivates a deactivated team member.
    """
    firm_permission = 'manage_team'

    def post(self, request, membership_id):
        membership = get_firm_object_or_404(FirmMembership, request.firm, id=membership_id)
        membership.status = MembershipStatus.ACTIVE
        membership.save(update_fields=['status'])

        log_audit(
            request=request,
            firm=request.firm,
            user=request.user,
            action='MEMBER_ACTIVATED',
            object_type='FirmMembership',
            object_id=str(membership.id),
            description=f"Reactivated team member {membership.user.email}",
        )
        messages.success(request, _(f"{membership.user.get_full_name()} has been reactivated."))
        return redirect('firms:team_list')


class TeamRevokeInviteView(PermissionRequiredMixin, View):
    """
    Cancels a pending invitation.
    """
    firm_permission = 'invite_team'

    def post(self, request, invitation_id):
        invitation = get_firm_object_or_404(FirmInvitation, request.firm, id=invitation_id)
        email = invitation.email
        invitation.delete()

        log_audit(
            request=request,
            firm=request.firm,
            user=request.user,
            action='INVITE_REVOKED',
            object_type='FirmInvitation',
            object_id=str(invitation_id),
            description=f"Revoked invitation for {email}",
        )
        messages.info(request, _(f"Invitation for {email} has been revoked."))
        return redirect('firms:team_list')


class AcceptInvitationView(View):
    """
    Public onboarding endpoint for accepting firm invitations.
    Handles existing user login or new user registration before attaching membership.
    """
    template_name = 'firms/invitation_accept.html'

    def get_invitation(self, token):
        return FirmInvitation.objects.select_related('firm', 'invited_by').filter(
            token=token,
            is_accepted=False,
        ).first()

    def get(self, request, token):
        invitation = self.get_invitation(token)
        if not invitation or invitation.is_expired:
            return render(request, 'firms/invitation_invalid.html', {
                'message': _("This invitation is invalid or has expired. Please request a new invitation.")
            })

        # If user is already authenticated
        if request.user.is_authenticated:
            return render(request, self.template_name, {
                'invitation': invitation,
                'is_authenticated': True,
                'user': request.user,
            })

        # Check if an account already exists with that email
        existing_user = User.objects.filter(email__iexact=invitation.email).first()
        form = AcceptInvitationRegistrationForm() if not existing_user else None

        return render(request, self.template_name, {
            'invitation': invitation,
            'is_authenticated': False,
            'existing_user': existing_user,
            'form': form,
        })

    def post(self, request, token):
        invitation = self.get_invitation(token)
        if not invitation or invitation.is_expired:
            messages.error(request, _("This invitation has expired or is invalid."))
            return redirect('accounts:login')

        if request.user.is_authenticated:
            # User is already signed in, accept directly
            accept_firm_invitation(request, invitation, request.user)
            messages.success(request, _(f"You have joined {invitation.firm.name} as {invitation.get_role_display()}!"))
            return redirect('core:dashboard')

        # Check existing user
        existing_user = User.objects.filter(email__iexact=invitation.email).first()
        if existing_user:
            # Must log in first
            messages.info(request, _("Please log in with your credentials to accept this invitation."))
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        # Register new user from invitation form
        form = AcceptInvitationRegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                email=invitation.email,
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                phone=data.get('phone', ''),
                is_active=True,
                is_email_verified=True,  # Verified via invitation link
            )
            login(request, user)
            accept_firm_invitation(request, invitation, user)
            messages.success(request, _(f"Welcome to CAFlow, {user.first_name}! You've joined {invitation.firm.name}."))
            return redirect('core:dashboard')

        return render(request, self.template_name, {
            'invitation': invitation,
            'is_authenticated': False,
            'existing_user': False,
            'form': form,
        })
