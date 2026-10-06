import logging
from audit.models import AuditLog

logger = logging.getLogger(__name__)


def log_audit(request=None, firm=None, user=None, action='', object_type='', object_id='', description=''):
    """
    Records an immutable audit event.
    Automatically infers user, firm, IP, and user-agent from request if present.
    """
    try:
        ip = None
        user_agent = ''

        if request is not None:
            if not user and getattr(request, 'user', None) and request.user.is_authenticated:
                user = request.user
            if not firm and getattr(request, 'firm', None):
                firm = request.firm

            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')

            user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]

        return AuditLog.objects.create(
            firm=firm,
            user=user if (user and user.is_authenticated) else None,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id else '',
            description=description,
            ip_address=ip,
            user_agent=user_agent,
        )
    except Exception as e:
        logger.warning(f"Could not record audit log: {e}")
        return None
