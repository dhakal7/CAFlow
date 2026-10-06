import secrets
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from firms.models import Firm, FirmMembership, FirmInvitation, FirmRole, MembershipStatus
from audit.services import log_audit


def get_firm_object_or_404(model_class, firm, **kwargs):
    """
    Safely retrieves an object strictly scoped to the specified firm.
    Raises Http404 if the object doesn't exist or belongs to a different tenant.
    Guarantees cross-tenant IDOR attacks are completely neutralized.
    """
    if not firm:
        raise Http404(_("No active firm specified."))
    try:
        return model_class.objects.get(firm=firm, **kwargs)
    except model_class.DoesNotExist:
        raise Http404(_(f"Requested {model_class._meta.verbose_name} not found in this practice workspace."))


def switch_active_firm(request, firm_id) -> Firm:
    """
    Switches the user's active workspace session to a target firm.
    Strictly verifies that the user is an active member of that target firm.
    Raises PermissionDenied (403) if the user has no active membership.
    """
    user = request.user
    if not user.is_authenticated:
        raise PermissionDenied(_("Authentication required to switch workspace."))

    membership = FirmMembership.objects.select_related('firm').filter(
        user=user,
        firm_id=firm_id,
        status=MembershipStatus.ACTIVE,
        firm__is_active=True,
    ).first()

    if not membership:
        raise PermissionDenied(_("You do not have access to this firm workspace."))

    request.session['active_firm_id'] = str(membership.firm.id)
    request.firm = membership.firm
    request.firm_membership = membership
    user._active_membership = membership

    log_audit(
        request=request,
        firm=membership.firm,
        user=user,
        action='VIEW',
        object_type='Firm',
        object_id=str(membership.firm.id),
        description=f"Switched active workspace to {membership.firm.name}",
    )

    return membership.firm


def create_firm_invitation(request, firm, email: str, role: str, invited_by) -> FirmInvitation:
    """
    Generates a secure, time-limited invitation token and dispatches an invite email.
    """
    email_clean = email.strip().lower()

    # Verify if user is already an active member of the firm
    existing_membership = FirmMembership.objects.filter(
        firm=firm,
        user__email__iexact=email_clean,
        status=MembershipStatus.ACTIVE,
    ).first()
    if existing_membership:
        raise ValueError(_("A user with this email is already an active member of this firm."))

    # Generate cryptographic token (64 hex chars)
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(days=7)

    # Cancel previous pending invitations for same email & firm
    FirmInvitation.objects.filter(
        firm=firm,
        email__iexact=email_clean,
        is_accepted=False,
    ).delete()

    invitation = FirmInvitation.objects.create(
        firm=firm,
        email=email_clean,
        role=role,
        token=token,
        invited_by=invited_by,
        expires_at=expires_at,
    )

    log_audit(
        request=request,
        firm=firm,
        user=invited_by,
        action='INVITE_SENT',
        object_type='FirmInvitation',
        object_id=str(invitation.id),
        description=f"Invited {email_clean} to join {firm.name} as {invitation.get_role_display()}",
    )

    # Dispatch email
    invite_url = request.build_absolute_uri(f"/invitations/accept/{token}/")
    subject = f"Invitation to join {firm.name} on CAFlow"
    body = f"""Namaste,

You have been invited by {invited_by.get_full_name()} to join {firm.name} on CAFlow Nepal as a {invitation.get_role_display()}.

Click the link below to accept your invitation and access your workspace:
{invite_url}

This invitation link will expire in 7 days.

Warm regards,
CAFlow Team
"""
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_clean],
            fail_silently=True,
        )
    except Exception:
        pass

    return invitation


def accept_firm_invitation(request, invitation: FirmInvitation, user) -> FirmMembership:
    """
    Accepts an invitation, assigns the role, and adds the user to the firm.
    """
    if invitation.is_accepted:
        raise ValueError(_("This invitation has already been accepted."))
    if invitation.is_expired:
        raise ValueError(_("This invitation link has expired."))

    membership, created = FirmMembership.objects.update_or_create(
        firm=invitation.firm,
        user=user,
        defaults={
            'role': invitation.role,
            'status': MembershipStatus.ACTIVE,
            'invited_by': invitation.invited_by,
        }
    )

    invitation.is_accepted = True
    invitation.accepted_at = timezone.now()
    invitation.save()

    request.session['active_firm_id'] = str(invitation.firm.id)

    log_audit(
        request=request,
        firm=invitation.firm,
        user=user,
        action='INVITE_ACCEPTED',
        object_type='FirmMembership',
        object_id=str(membership.id),
        description=f"{user.get_full_name()} accepted invitation and joined {invitation.firm.name} as {membership.get_role_display()}",
    )

    return membership
