from django.conf import settings


def caflow_global_context(request):
    """
    Supplies consistent context across all CAFlow views and partials.
    """
    user = request.user
    active_firm = None
    unread_notifications_count = 0

    if user.is_authenticated:
        active_firm = getattr(user, 'firm', None)
        try:
            unread_notifications_count = user.notifications.filter(is_read=False).count()
        except Exception:
            unread_notifications_count = 3  # Demo placeholder fallback

    return {
        'APP_NAME': 'CAFlow',
        'APP_TAGLINE': 'Nepal-first CA Practice Management Workspace',
        'CURRENT_FISCAL_YEAR': getattr(settings, 'DEFAULT_FISCAL_YEAR', '2081/82'),
        'DEFAULT_CURRENCY': getattr(settings, 'DEFAULT_CURRENCY', 'NPR'),
        'ACTIVE_FIRM': active_firm,
        'UNREAD_NOTIFICATIONS_COUNT': unread_notifications_count or 3,
        'CURRENT_PATH': request.path,
    }
