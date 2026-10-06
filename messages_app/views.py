from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from firms.mixins import FirmRequiredMixin
from firms.models import FirmRole


class InboxView(FirmRequiredMixin, TemplateView):
    template_name = 'messages_app/inbox.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not getattr(request, 'firm', None):
            return super().dispatch(request, *args, **kwargs)
        if request.firm_membership and request.firm_membership.role == FirmRole.CLIENT:
            raise PermissionDenied(_("Client users do not have access to internal practice messages."))
        return super().dispatch(request, *args, **kwargs)


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['breadcrumbs'] = [
            {'title': 'Messages', 'url': ''},
        ]
        return context

