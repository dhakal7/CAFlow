from functools import wraps
from django.conf import settings
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


def firm_required(view_func):
    """Decorator ensuring user is authenticated and attached to an active firm."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if _is_json_request(request):
                return JsonResponse({'error': 'Authentication required.', 'code': 'UNAUTHENTICATED'}, status=401)
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        if not getattr(request, 'firm', None) or not getattr(request, 'firm_membership', None):
            if _is_json_request(request):
                return JsonResponse({'error': 'Active firm workspace required.', 'code': 'NO_ACTIVE_FIRM'}, status=403)
            return redirect('firms:no_firm')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def role_required(allowed_roles):
    """Decorator requiring one of the specified roles in the active firm."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _is_json_request(request):
                    return JsonResponse({'error': 'Authentication required.', 'code': 'UNAUTHENTICATED'}, status=401)
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            if not getattr(request, 'firm', None):
                if _is_json_request(request):
                    return JsonResponse({'error': 'Active firm workspace required.', 'code': 'NO_ACTIVE_FIRM'}, status=403)
                return redirect('firms:no_firm')
            if not request.firm_membership or request.firm_membership.role not in allowed_roles:
                if _is_json_request(request):
                    return JsonResponse(
                        {'error': 'Your assigned practice role does not have authorization to access this area.', 'code': 'ROLE_FORBIDDEN'},
                        status=403
                    )
                raise PermissionDenied(
                    _("Your assigned practice role does not have authorization to access this area.")
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def permission_required(permission_name: str):
    """Decorator requiring a specific firm permission."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _is_json_request(request):
                    return JsonResponse({'error': 'Authentication required.', 'code': 'UNAUTHENTICATED'}, status=401)
                return redirect(f"{settings.LOGIN_URL}?next={request.path}")
            if not getattr(request, 'firm', None):
                if _is_json_request(request):
                    return JsonResponse({'error': 'Active firm workspace required.', 'code': 'NO_ACTIVE_FIRM'}, status=403)
                return redirect('firms:no_firm')
            if not has_firm_permission(request.user, request.firm, permission_name):
                if _is_json_request(request):
                    return JsonResponse(
                        {'error': 'You lack the required practice permission to perform this action.', 'code': 'PERMISSION_DENIED'},
                        status=403
                    )
                raise PermissionDenied(
                    _("You lack the required practice permission to perform this action.")
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

