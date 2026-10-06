from django.utils.deprecation import MiddlewareMixin
from firms.models import FirmMembership, MembershipStatus
from firms.permissions import has_firm_permission, has_any_firm_permission, get_user_firm_permissions


class TenantMiddleware(MiddlewareMixin):
    """
    Multi-tenant isolation middleware.
    Resolves and verifies the authenticated user's active firm workspace.
    Guarantees request.firm is strictly validated server-side against database memberships.
    """
    def process_request(self, request):
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated or not getattr(user, 'is_active', False):
            request.firm = None
            request.firm_membership = None
            request.has_firm_perm = lambda perm: False
            request.has_any_firm_perm = lambda perms: False
            request.firm_permissions = set()
            return None

        active_firm_id = request.session.get('active_firm_id')
        membership = None

        if active_firm_id:
            membership = FirmMembership.objects.select_related('firm').filter(
                user=user,
                firm_id=active_firm_id,
                status=MembershipStatus.ACTIVE,
                is_active=True,
                firm__is_active=True,
            ).first()

        # Fallback to the first active membership if session key is absent or invalid
        if not membership:
            membership = FirmMembership.objects.select_related('firm').filter(
                user=user,
                status=MembershipStatus.ACTIVE,
                is_active=True,
                firm__is_active=True,
            ).order_by('joined_at').first()

            if membership:
                request.session['active_firm_id'] = str(membership.firm_id)
            elif active_firm_id:
                request.session.pop('active_firm_id', None)

        if membership:
            request.firm = membership.firm
            request.firm_membership = membership
            user._active_membership = membership
            request.firm_permissions = get_user_firm_permissions(user, membership.firm)
            request.has_firm_perm = lambda perm: has_firm_permission(user, membership.firm, perm)
            request.has_any_firm_perm = lambda perms: has_any_firm_permission(user, membership.firm, perms)
        else:
            request.firm = None
            request.firm_membership = None
            user._active_membership = None
            request.firm_permissions = set()
            request.has_firm_perm = lambda perm: False
            request.has_any_firm_perm = lambda perms: False

        return None

