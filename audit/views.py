from django.views.generic import TemplateView
from firms.mixins import PermissionRequiredMixin


class AuditListView(PermissionRequiredMixin, TemplateView):
    firm_permission = 'view_audit_logs'
    template_name = 'audit/audit_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Audit Logs', 'url': ''},
        ]
        return context
