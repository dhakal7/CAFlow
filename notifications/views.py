from django.contrib import messages
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView

from firms.mixins import FirmRequiredMixin
from notifications.models import Notification


class NotificationListView(FirmRequiredMixin, ListView):
    """
    Displays live alerts and notifications for the authenticated user
    within their active practice organization.
    """
    model = Notification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 30

    def get_queryset(self):
        user = self.request.user
        firm = self.request.firm
        qs = Notification.objects.filter(recipient=user).filter(
            models.Q(firm=firm) | models.Q(firm__isnull=True)
        )
        filter_type = self.request.GET.get('type', 'all')
        if filter_type == 'unread':
            qs = qs.filter(is_read=False)
        elif filter_type == 'TASK':
            qs = qs.filter(notification_type=Notification.NotificationType.TASK)
        elif filter_type == 'COMPLIANCE':
            qs = qs.filter(notification_type=Notification.NotificationType.COMPLIANCE)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        firm = self.request.firm
        base_qs = Notification.objects.filter(recipient=user).filter(
            models.Q(firm=firm) | models.Q(firm__isnull=True)
        )
        context.update({
            'breadcrumbs': [{'title': 'Notifications', 'url': ''}],
            'total_count': base_qs.count(),
            'unread_count': base_qs.filter(is_read=False).count(),
            'task_count': base_qs.filter(notification_type=Notification.NotificationType.TASK).count(),
            'compliance_count': base_qs.filter(notification_type=Notification.NotificationType.COMPLIANCE).count(),
            'current_filter': self.request.GET.get('type', 'all'),
        })
        return context


class NotificationMarkAllReadView(FirmRequiredMixin, View):
    """
    Marks all notifications for the current user as read.
    """
    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )
        messages.success(request, _("All notifications marked as read."))
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect('notifications:notification_list')


class NotificationMarkReadView(FirmRequiredMixin, View):
    """
    Marks an individual notification as read and redirects to action_url if present.
    """
    def post(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect(notification.action_url or 'notifications:notification_list')
