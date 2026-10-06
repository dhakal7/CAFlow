import logging
from notifications.models import Notification

logger = logging.getLogger(__name__)


def create_notification(
    recipient,
    title,
    message,
    notification_type=Notification.NotificationType.TASK,
    firm=None,
    action_url='',
):
    """
    Creates an in-app notification for a user.
    Strictly isolated and safe.
    """
    if not recipient:
        return None

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            firm=firm,
            title=title,
            message=message,
            notification_type=notification_type,
            action_url=action_url,
        )
        return notification
    except Exception as e:
        logger.error(f"Failed to create notification for {recipient}: {e}")
        return None
