from django.views.generic import TemplateView


class ReportDashboardView(TemplateView):
    template_name = 'reports/report_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Reports', 'url': ''},
        ]
        return context
