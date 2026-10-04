from django.views.generic import TemplateView


class ClientListView(TemplateView):
    template_name = 'clients/client_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Clients', 'url': ''},
        ]
        return context
