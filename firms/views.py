from django.views.generic import TemplateView


class TeamListView(TemplateView):
    template_name = 'firms/team_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Admin', 'url': ''},
            {'title': 'Practice Team', 'url': ''},
        ]
        return context


class FirmSettingsView(TemplateView):
    template_name = 'firms/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Admin', 'url': ''},
            {'title': 'Firm Settings', 'url': ''},
        ]
        return context
