from django.views.generic import TemplateView
from firms.mixins import PermissionRequiredMixin


class ReportDashboardView(PermissionRequiredMixin, TemplateView):
    firm_permission = 'view_reports'
    template_name = 'reports/report_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Reports', 'url': ''},
        ]
        return context
