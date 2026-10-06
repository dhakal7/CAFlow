from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from firms.permissions import has_firm_permission, has_firm_role


def _is_json_request(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or getattr(request, 'content_type', '') == 'application/json'
    )


class FirmRequiredMixin(LoginRequiredMixin):
    """
    Ensures the user is authenticated and is an active member of an active Firm.
    If no active firm can be resolved, redirects cleanly to the workspace resolution empty-state.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            if _is_json_request(request):
                return JsonResponse({'error': 'Authentication required.', 'code': 'UNAUTHENTICATED'}, status=401)
            return self.handle_no_permission()

        if not getattr(request, 'firm', None) or not getattr(request, 'firm_membership', None):
            if _is_json_request(request):
                return JsonResponse({'error': 'Active firm workspace required.', 'code': 'NO_ACTIVE_FIRM'}, status=403)
            return redirect('firms:no_firm')

        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(FirmRequiredMixin):
    """
    Ensures the user holds one of the specified roles within their active firm.
    Authorization is validated before executing any view action.
    Raises PermissionDenied (403) or returns 403 JSON on unauthorized attempts.
    """
    allowed_roles: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            if _is_json_request(request):
                return JsonResponse({'error': 'Authentication required.', 'code': 'UNAUTHENTICATED'}, status=401)
            return self.handle_no_permission()

        if not getattr(request, 'firm', None) or not getattr(request, 'firm_membership', None):
            if _is_json_request(request):
                return JsonResponse({'error': 'Active firm workspace required.', 'code': 'NO_ACTIVE_FIRM'}, status=403)
            return redirect('firms:no_firm')

        if not request.firm_membership or request.firm_membership.role not in self.allowed_roles:
            if _is_json_request(request):
                return JsonResponse(
                    {'error': 'Your assigned practice role does not have authorization to access this area.', 'code': 'ROLE_FORBIDDEN'},
                    status=403
                )
            raise PermissionDenied(
                _("Your assigned practice role does not have authorization to access this area.")
            )

        return super(FirmRequiredMixin, self).dispatch(request, *args, **kwargs)


class PermissionRequiredMixin(FirmRequiredMixin):
    """
    Ensures the user has the explicit firm permission required for this view.
    Authorization is validated before executing any view action.
    Raises PermissionDenied (403) or returns 403 JSON on unauthorized attempts.
    """
    firm_permission: str = ''

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            if _is_json_request(request):
                return JsonResponse({'error': 'Authentication required.', 'code': 'UNAUTHENTICATED'}, status=401)
            return self.handle_no_permission()

        if not getattr(request, 'firm', None) or not getattr(request, 'firm_membership', None):
            if _is_json_request(request):
                return JsonResponse({'error': 'Active firm workspace required.', 'code': 'NO_ACTIVE_FIRM'}, status=403)
            return redirect('firms:no_firm')

        if not self.firm_permission or not has_firm_permission(request.user, request.firm, self.firm_permission):
            if _is_json_request(request):
                return JsonResponse(
                    {'error': 'You lack the required practice permission to perform this action.', 'code': 'PERMISSION_DENIED'},
                    status=403
                )
            raise PermissionDenied(
                _("You lack the required practice permission to perform this action.")
            )

        return super(FirmRequiredMixin, self).dispatch(request, *args, **kwargs)

