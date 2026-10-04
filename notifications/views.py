from django.views.generic import TemplateView


class NotificationListView(TemplateView):
    template_name = 'notifications/notification_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Notifications', 'url': ''},
        ]
        return context
