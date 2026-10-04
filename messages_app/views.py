from django.views.generic import TemplateView


class InboxView(TemplateView):
    template_name = 'messages_app/inbox.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Messages', 'url': ''},
        ]
        return context
