from django.contrib.auth import logout
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView


class LoginView(DjangoLoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('core:dashboard')


from django.views import View

class LogoutView(View):
    def dispatch(self, request, *args, **kwargs):
        logout(request)
        return redirect('core:landing')


class ProfileView(TemplateView):
    template_name = 'accounts/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Account', 'url': ''},
            {'title': 'Profile', 'url': ''},
        ]
        return context
