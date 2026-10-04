from django.views.generic import TemplateView


class TaskListView(TemplateView):
    template_name = 'tasks/task_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Tasks', 'url': ''},
        ]
        return context
