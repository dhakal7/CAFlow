from django.views.generic import TemplateView


class LandingPageView(TemplateView):
    template_name = 'core/landing.html'


class DashboardView(TemplateView):
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Dashboard', 'url': ''}
        ]
        return context


class DesignSystemView(TemplateView):
    template_name = 'core/design_system.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Design System', 'url': ''}
        ]
        return context
