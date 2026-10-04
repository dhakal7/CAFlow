from django.views.generic import TemplateView


class CalendarView(TemplateView):
    template_name = 'calendar_app/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Calendar', 'url': ''},
        ]
        return context
