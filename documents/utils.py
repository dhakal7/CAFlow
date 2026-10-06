import os
import mimetypes
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from clients.models import Client
from documents.models import Document, DocumentRequest


def get_user_client(user, firm):
    """
    Resolves the Client entity associated with a portal user within the given firm.
    Matches by direct portal_user link or email match.
    """
    if not user or not user.is_authenticated or not firm:
        return None

    # 1. Direct portal_user link
    client = Client.objects.filter(firm=firm, portal_user=user).first()
    if client:
        return client

    # 2. Direct email match
    if getattr(user, 'email', None):
        client = Client.objects.filter(firm=firm, email__iexact=user.email).first()
        if client:
            return client

    return None


def get_firm_document_or_404(request, document_id):
    """
    Strictly tenant-scoped document lookup.
    Prevents cross-firm access and restricts client users to their own documents.
    """
    firm = getattr(request, 'firm', None)
    if not firm:
        raise PermissionDenied(_("Active firm workspace required."))

    doc = get_object_or_404(Document.objects.select_related('client', 'uploaded_by', 'firm'), id=document_id, firm=firm)

    # If user is a portal client user, ensure they can only view documents for their entity
    if getattr(request.user, 'is_client_user', False):
        client = get_user_client(request.user, firm)
        if not client or doc.client_id != client.id:
            raise PermissionDenied(_("You do not have permission to access this document."))

    return doc


def get_firm_document_request_or_404(request, request_id):
    """
    Strictly tenant-scoped document request lookup.
    Prevents cross-firm access and restricts client users to their own requests.
    """
    firm = getattr(request, 'firm', None)
    if not firm:
        raise PermissionDenied(_("Active firm workspace required."))

    doc_req = get_object_or_404(
        DocumentRequest.objects.select_related('client', 'requested_by', 'uploaded_document', 'firm'),
        id=request_id,
        firm=firm,
    )

    if getattr(request.user, 'is_client_user', False):
        client = get_user_client(request.user, firm)
        if not client or doc_req.client_id != client.id:
            raise PermissionDenied(_("You do not have permission to access this document request."))

    return doc_req


def get_safe_mime_type(file_path):
    """Returns safe MIME type or fallback octet-stream."""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'
