from django.views.generic import TemplateView


class ComplianceDeadlineListView(TemplateView):
    template_name = 'compliance/compliance_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Compliance', 'url': ''},
        ]
        return context
