"""
CAFlow Scalable Role-Based Permission Architecture.
Guarantees server-side authorization enforcement across firms and roles.
"""

from typing import Iterable, Set


ALL_PERMISSIONS = {
    # Clients
    'view_client': 'View client profile and records',
    'create_client': 'Create new client entity',
    'edit_client': 'Edit existing client details and tax info',
    'delete_client': 'Delete or archive client',
    # Tasks
    'view_task': 'View practice tasks',
    'create_task': 'Create new work task',
    'edit_task': 'Update task status and details',
    'delete_task': 'Delete task',
    'assign_task': 'Assign tasks to team members',
    # Documents
    'view_document': 'View uploaded documents',
    'upload_document': 'Upload working papers and vouchers',
    'download_document': 'Download client documents',
    'delete_document': 'Delete documents',
    'request_document': 'Request document from client portal',
    # Compliance
    'view_compliance': 'View IRD, OCR, and ICAN compliance calendar',
    'manage_compliance': 'Update compliance filings and statuses',
    # Team
    'view_team': 'View practice team roster and roles',
    'invite_team': 'Send invitations to new team members',
    'manage_team': 'Modify member roles and deactivate accounts',
    # Billing
    'view_billing': 'View client invoices and billing history',
    'manage_billing': 'Issue invoices, record payments, and manage fees',
    # Reports
    'view_reports': 'Access practice analytics, MIS, and realization reports',
    # Settings
    'manage_settings': 'Configure firm profile, PAN, logo, and preferences',
    # Audit
    'view_audit_logs': 'Inspect security, compliance, and access audit logs',
}


# Explicit Role Permission Sets
ROLE_PERMISSIONS: dict[str, Set[str]] = {
    # OWNER: Absolute control over the firm practice
    'OWNER': set(ALL_PERMISSIONS.keys()),

    # ADMIN: Practice administration and team management
    'ADMIN': {
        'view_client', 'create_client', 'edit_client', 'delete_client',
        'view_task', 'create_task', 'edit_task', 'delete_task', 'assign_task',
        'view_document', 'upload_document', 'download_document', 'delete_document', 'request_document',
        'view_compliance', 'manage_compliance',
        'view_team', 'invite_team', 'manage_team',
        'view_billing', 'manage_billing',
        'view_reports',
        'manage_settings',
        'view_audit_logs',
    },

    # CA: CA-level access to clients, documents, tasks and compliance
    'CA': {
        'view_client', 'create_client', 'edit_client',
        'view_task', 'create_task', 'edit_task', 'assign_task',
        'view_document', 'upload_document', 'download_document', 'request_document',
        'view_compliance', 'manage_compliance',
        'view_team',
        'view_billing',
        'view_reports',
    },

    # SENIOR: Senior associate with broad operational access
    'SENIOR': {
        'view_client', 'create_client', 'edit_client',
        'view_task', 'create_task', 'edit_task', 'assign_task',
        'view_document', 'upload_document', 'download_document', 'request_document',
        'view_compliance', 'manage_compliance',
        'view_team',
        'view_reports',
    },

    # ACCOUNTANT: Accounting and assigned operational work
    'ACCOUNTANT': {
        'view_client',
        'view_task', 'create_task', 'edit_task',
        'view_document', 'upload_document', 'download_document',
        'view_compliance',
        'view_team',
        'view_billing',
    },

    # STAFF: Limited operational access
    'STAFF': {
        'view_client',
        'view_task', 'edit_task',
        'view_document', 'upload_document', 'download_document',
        'view_compliance',
    },

    # CLIENT: Strictly client portal access (isolated from firm internals)
    'CLIENT': set(),
}


def get_user_membership(user, firm):
    """Fetches the active membership of a user in a given firm."""
    if not user or not user.is_authenticated or not getattr(user, 'is_active', False) or not firm:
        return None

    # Check cached membership on user
    cached_m = getattr(user, '_active_membership', None)
    if (
        cached_m
        and cached_m.firm_id == firm.id
        and cached_m.status == 'ACTIVE'
        and getattr(cached_m, 'is_active', True)
        and getattr(cached_m.firm, 'is_active', True)
    ):
        return cached_m

    from firms.models import FirmMembership, MembershipStatus
    return FirmMembership.objects.select_related('firm').filter(
        user=user,
        firm=firm,
        status=MembershipStatus.ACTIVE,
        is_active=True,
        firm__is_active=True,
    ).first()



def has_firm_permission(user, firm, permission_name: str) -> bool:
    """
    Checks if a user has a specific permission in the designated firm.
    Superusers bypass role restrictions.
    """
    if not user or not user.is_authenticated or not getattr(user, 'is_active', False):
        return False
    if user.is_superuser:
        return True
    if not firm:
        return False

    membership = get_user_membership(user, firm)
    if not membership:
        return False

    allowed_perms = ROLE_PERMISSIONS.get(membership.role, set())
    return permission_name in allowed_perms


def has_any_firm_permission(user, firm, permission_names: Iterable[str]) -> bool:
    """Checks if a user has at least one of the given permissions in a firm."""
    return any(has_firm_permission(user, firm, perm) for perm in permission_names)


def has_firm_role(user, firm, allowed_roles: Iterable[str]) -> bool:
    """Checks if a user possesses one of the allowed roles in a firm."""
    if not user or not user.is_authenticated or not getattr(user, 'is_active', False):
        return False
    if user.is_superuser:
        return True
    if not firm:
        return False

    membership = get_user_membership(user, firm)
    if not membership:
        return False

    return membership.role in allowed_roles


def get_user_firm_permissions(user, firm) -> Set[str]:
    """Returns the set of all permission strings the user possesses in a firm."""
    if not user or not user.is_authenticated or not getattr(user, 'is_active', False) or not firm:
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSIONS.keys())

    membership = get_user_membership(user, firm)
    if not membership:
        return set()

    return ROLE_PERMISSIONS.get(membership.role, set())
