from django.views.generic import TemplateView
from firms.mixins import PermissionRequiredMixin


class InvoiceListView(PermissionRequiredMixin, TemplateView):
    firm_permission = 'view_billing'
    template_name = 'billing/invoice_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Billing', 'url': ''},
        ]
        return context
