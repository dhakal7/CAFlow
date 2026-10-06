from django.conf import settings
from firms.models import FirmMembership, MembershipStatus
from clients.models import Client
from tasks.models import Task
from compliance.models import ComplianceDeadline


def caflow_global_context(request):
    """
    Supplies consistent context across all CAFlow views and partials.
    Provides authenticated user firm scope, permissions, practice info,
    and live sidebar entity statistics from database.
    """
    user = getattr(request, 'user', None)
    active_firm = getattr(request, 'firm', None)
    membership = getattr(request, 'firm_membership', None)
    user_firms = []
    firm_permissions = getattr(request, 'firm_permissions', set())
    unread_notifications_count = 0
    sidebar_client_count = None
    sidebar_task_count = None
    sidebar_compliance_count = None

    if user and user.is_authenticated and getattr(user, 'is_active', False):
        try:
            # Query all firms the user belongs to for workspace switcher
            user_firms = list(FirmMembership.objects.select_related('firm').filter(
                user=user,
                status=MembershipStatus.ACTIVE,
                firm__is_active=True,
            ).order_by('firm__name'))
        except Exception:
            user_firms = []

        try:
            unread_notifications_count = user.notifications.filter(is_read=False).count()
        except Exception:
            unread_notifications_count = 0

        if active_firm:
            try:
                sidebar_client_count = Client.objects.filter(firm=active_firm).exclude(status=Client.Status.ARCHIVED).count()
                sidebar_task_count = Task.objects.filter(firm=active_firm).exclude(status=Task.Status.COMPLETED).count()
                sidebar_compliance_count = ComplianceDeadline.objects.filter(firm=active_firm).exclude(
                    status__in=[ComplianceDeadline.Status.COMPLETED, ComplianceDeadline.Status.FILED, ComplianceDeadline.Status.CANCELLED]
                ).count()
            except Exception:
                pass

    return {
        'APP_NAME': 'CAFlow',
        'APP_TAGLINE': 'Nepal-first CA Practice Management Workspace',
        'CURRENT_FISCAL_YEAR': getattr(active_firm, 'current_fiscal_year', None) or getattr(settings, 'DEFAULT_FISCAL_YEAR', '2081/82'),
        'DEFAULT_CURRENCY': getattr(active_firm, 'currency', None) or getattr(settings, 'DEFAULT_CURRENCY', 'NPR'),
        'ACTIVE_FIRM': active_firm,
        'USER_MEMBERSHIP': membership,
        'USER_ROLE': membership.role if membership else None,
        'USER_FIRMS': user_firms,
        'USER_PERMISSIONS': firm_permissions,
        'UNREAD_NOTIFICATIONS_COUNT': unread_notifications_count,
        'SIDEBAR_CLIENT_COUNT': sidebar_client_count,
        'SIDEBAR_TASK_COUNT': sidebar_task_count,
        'SIDEBAR_COMPLIANCE_COUNT': sidebar_compliance_count,
        'CURRENT_PATH': request.path,
    }

