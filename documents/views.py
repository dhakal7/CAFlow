from django.views.generic import TemplateView


class DocumentListView(TemplateView):
    template_name = 'documents/document_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Documents', 'url': ''},
        ]
        return context
