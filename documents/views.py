import os
from datetime import timedelta
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView

from audit.models import AuditLog
from audit.services import log_audit
from clients.models import Client, ClientActivity
from documents.forms import (
    ClientPortalFulfillRequestForm,
    DocumentEditForm,
    DocumentRequestForm,
    DocumentRequestStatusForm,
    DocumentUploadForm,
    FISCAL_YEAR_CHOICES,
)
from documents.models import Document, DocumentRequest
from documents.utils import (
    get_firm_document_or_404,
    get_firm_document_request_or_404,
    get_safe_mime_type,
    get_user_client,
)
from firms.mixins import FirmRequiredMixin, PermissionRequiredMixin
from firms.models import FirmRole


class DocumentListView(FirmRequiredMixin, ListView):
    """
    Firm & Client Document Vault.
    Strictly isolated to request.firm with search, filtering, sorting, and pagination.
    Redirects external client portal users to their dedicated document portal.
    """
    model = Document
    template_name = 'documents/document_list.html'
    context_object_name = 'documents'
    paginate_by = 15

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # If user is a portal client user, redirect to client portal requests view
        if getattr(request.user, 'is_client_user', False):
            return redirect('documents:portal_requests')

        # Internal staff must have view_document permission
        if not request.has_firm_perm('view_document'):
            raise PermissionDenied(_("You lack the required permission to access the document vault."))

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        firm = self.request.firm
        active_tab = self.request.GET.get('tab', 'vault').lower()

        # Base queryset for firm
        qs = Document.objects.filter(firm=firm).select_related('client', 'uploaded_by')

        # Status filter: default to ACTIVE unless tab=archived or status is explicitly set
        status_param = self.request.GET.get('status', '').strip().upper()
        if active_tab == 'archived':
            qs = qs.filter(status=Document.Status.ARCHIVED)
        elif status_param == 'ARCHIVED':
            qs = qs.filter(status=Document.Status.ARCHIVED)
        elif status_param == 'ALL':
            pass
        else:
            qs = qs.filter(status=Document.Status.ACTIVE)

        # 1. Search Query
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(client__name__icontains=q)
                | Q(client__business_name__icontains=q)
                | Q(client__pan_number__icontains=q)
                | Q(uploaded_by__first_name__icontains=q)
                | Q(uploaded_by__last_name__icontains=q)
                | Q(description__icontains=q)
            )

        # 2. Category Filter
        category = self.request.GET.get('category', '').strip()
        if category and category != 'ALL':
            qs = qs.filter(category=category)

        # 3. Client Filter
        client_id = self.request.GET.get('client', '').strip()
        if client_id and client_id != 'ALL':
            qs = qs.filter(client_id=client_id)

        # 4. Fiscal Year Filter
        fy = self.request.GET.get('fiscal_year', '').strip()
        if fy and fy != 'ALL':
            qs = qs.filter(fiscal_year=fy)

        # 5. Expiry Filter
        expiry_filter = self.request.GET.get('expiry', '').strip().lower()
        today = timezone.localdate()
        if expiry_filter == 'expired':
            qs = qs.filter(expiry_date__isnull=False, expiry_date__lt=today)
        elif expiry_filter == 'expiring_soon':
            qs = qs.filter(expiry_date__isnull=False, expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30))
        elif expiry_filter == 'has_expiry':
            qs = qs.filter(expiry_date__isnull=False)

        # 6. Sorting
        sort_by = self.request.GET.get('sort', '-created_at').strip()
        valid_sorts = {
            '-created_at': '-created_at',
            'created_at': 'created_at',
            'title': 'title',
            '-title': '-title',
            'file_size': 'file_size_bytes',
            '-file_size': '-file_size_bytes',
            'expiry': 'expiry_date',
        }
        qs = qs.order_by(valid_sorts.get(sort_by, '-created_at'))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm
        today = timezone.localdate()

        active_tab = self.request.GET.get('tab', 'vault').lower()
        context['active_tab'] = active_tab

        # Metrics & Summary Statistics
        all_firm_docs = Document.objects.filter(firm=firm)
        active_docs = all_firm_docs.filter(status=Document.Status.ACTIVE)
        archived_docs_count = all_firm_docs.filter(status=Document.Status.ARCHIVED).count()

        total_storage_bytes = active_docs.aggregate(total=Sum('file_size_bytes'))['total'] or 0
        total_storage_mb = round(total_storage_bytes / (1024 * 1024), 2)

        # Document Requests stats
        all_requests = DocumentRequest.objects.filter(firm=firm)
        pending_requests_count = all_requests.filter(
            status__in=[DocumentRequest.Status.REQUESTED, DocumentRequest.Status.PENDING, DocumentRequest.Status.PARTIALLY_RECEIVED, DocumentRequest.Status.REMINDED]
        ).count()
        overdue_requests_count = all_requests.filter(
            status__in=[DocumentRequest.Status.REQUESTED, DocumentRequest.Status.PENDING, DocumentRequest.Status.OVERDUE, DocumentRequest.Status.REMINDED],
            due_date__lt=today,
        ).count()

        # Expiring documents count
        expiring_docs_count = active_docs.filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        ).count()

        context['stats'] = {
            'total_active_docs': active_docs.count(),
            'total_storage_mb': total_storage_mb,
            'archived_count': archived_docs_count,
            'pending_requests': pending_requests_count,
            'overdue_requests': overdue_requests_count,
            'expiring_docs': expiring_docs_count,
        }

        # Query and filter state
        context['current_q'] = self.request.GET.get('q', '').strip()
        context['current_category'] = self.request.GET.get('category', 'ALL')
        context['current_client'] = self.request.GET.get('client', 'ALL')
        context['current_fiscal_year'] = self.request.GET.get('fiscal_year', 'ALL')
        context['current_status'] = self.request.GET.get('status', 'ALL')
        context['current_expiry'] = self.request.GET.get('expiry', 'ALL')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')

        # Dropdown options
        context['categories'] = Document.Category.choices
        context['clients_list'] = Client.objects.filter(firm=firm, is_active=True).order_by('name')
        context['fiscal_year_choices'] = FISCAL_YEAR_CHOICES

        # Form instances for modals
        context['upload_form'] = DocumentUploadForm(firm=firm)
        context['request_form'] = DocumentRequestForm(firm=firm)

        # If on Requests tab, include firm document requests
        if active_tab == 'requests':
            req_qs = all_requests.select_related('client', 'requested_by', 'uploaded_document')
            req_status = self.request.GET.get('req_status', '').strip().upper()
            if req_status and req_status != 'ALL':
                req_qs = req_qs.filter(status=req_status)
            if context['current_client'] and context['current_client'] != 'ALL':
                req_qs = req_qs.filter(client_id=context['current_client'])
            if context['current_q']:
                req_qs = req_qs.filter(
                    Q(requested_documents__icontains=context['current_q'])
                    | Q(client__name__icontains=context['current_q'])
                    | Q(client__business_name__icontains=context['current_q'])
                )
            context['requests_list'] = req_qs.order_by('due_date', '-created_at')
            context['request_status_choices'] = DocumentRequest.Status.choices

        context['breadcrumbs'] = [
            {'title': 'Documents', 'url': ''},
        ]
        return context


class DocumentRequestsListView(FirmRequiredMixin, ListView):
    """
    Dedicated view for Document Requests tracking.
    """
    model = DocumentRequest
    template_name = 'documents/request_list.html'
    context_object_name = 'requests'
    paginate_by = 15

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if getattr(request.user, 'is_client_user', False):
            return redirect('documents:portal_requests')
        if not request.has_firm_perm('view_document') and not request.has_firm_perm('request_document'):
            raise PermissionDenied(_("You lack permission to view document requests."))
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        firm = self.request.firm
        qs = DocumentRequest.objects.filter(firm=firm).select_related('client', 'requested_by', 'uploaded_document')

        status_param = self.request.GET.get('status', '').strip().upper()
        if status_param and status_param != 'ALL':
            qs = qs.filter(status=status_param)

        client_id = self.request.GET.get('client', '').strip()
        if client_id and client_id != 'ALL':
            qs = qs.filter(client_id=client_id)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(requested_documents__icontains=q)
                | Q(client__name__icontains=q)
                | Q(client__business_name__icontains=q)
            )

        return qs.order_by('due_date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm
        context['breadcrumbs'] = [
            {'title': 'Documents', 'url': reverse('documents:document_list')},
            {'title': 'Document Requests', 'url': ''},
        ]
        context['request_form'] = DocumentRequestForm(firm=firm)
        context['clients_list'] = Client.objects.filter(firm=firm, is_active=True).order_by('name')
        context['status_choices'] = DocumentRequest.Status.choices
        context['current_status'] = self.request.GET.get('status', 'ALL')
        context['current_client'] = self.request.GET.get('client', 'ALL')
        context['current_q'] = self.request.GET.get('q', '').strip()
        return context


class DocumentUploadView(PermissionRequiredMixin, View):
    """
    Firm-scoped document upload endpoint.
    Handles standard uploads from vault or client workspace.
    """
    firm_permission = 'upload_document'

    def post(self, request):
        firm = request.firm
        form = DocumentUploadForm(request.POST, request.FILES, firm=firm)

        if not form.is_valid():
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.title()}: {err}")
            return redirect(request.POST.get('next') or reverse('documents:document_list'))

        doc = form.save(commit=False)
        doc.firm = firm
        doc.uploaded_by = request.user
        doc.status = Document.Status.ACTIVE
        doc.save()

        # Create Client CRM activity record
        ClientActivity.objects.create(
            firm=firm,
            client=doc.client,
            activity_type=ClientActivity.ActivityType.DOC_UPLOADED,
            description=f"Uploaded working paper '{doc.title}' ({doc.get_category_display()}) for FY {doc.fiscal_year}.",
            performed_by=request.user,
        )

        # Immutable security audit entry
        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='Document',
            object_id=str(doc.id),
            description=f"Uploaded document '{doc.title}' ({doc.file_size_bytes} bytes) for client {doc.client.display_business_name}.",
        )

        msg = _(f"Document '{doc.title}' uploaded successfully.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg), 'document_id': str(doc.id)})

        messages.success(request, msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list'))


class DocumentDownloadView(FirmRequiredMixin, View):
    """
    Secure, firm-scoped document download handler.
    Strictly prevents cross-firm access, validates permissions, and records audit logs.
    """
    def get(self, request, document_id):
        # 1. Tenant & Permission Isolation check
        doc = get_firm_document_or_404(request, document_id)

        # 2. Check download permission for internal staff
        if not getattr(request.user, 'is_client_user', False):
            if not request.has_firm_perm('download_document') and not request.has_firm_perm('view_document'):
                raise PermissionDenied(_("You do not have permission to download documents."))

        # 3. Check physical file existence on disk
        if not doc.file or not os.path.exists(doc.file.path):
            log_audit(
                request=request,
                action=AuditLog.ActionType.VIEW,
                object_type='Document',
                object_id=str(doc.id),
                description=f"Attempted to download document '{doc.title}' but physical file was missing on disk.",
            )
            messages.error(request, _("The requested document file could not be found on the server repository."))
            return redirect(request.META.get('HTTP_REFERER') or reverse('documents:document_list'))

        # 4. Record audit log
        log_audit(
            request=request,
            action=AuditLog.ActionType.EXPORT,
            object_type='Document',
            object_id=str(doc.id),
            description=f"Downloaded confidential document '{doc.title}' ({doc.file_size_bytes} bytes) for client {doc.client.display_business_name}.",
        )

        # 5. Sanitize filename for download
        ext = doc.file_extension
        clean_title = slugify(doc.title) or 'document'
        download_name = f"{clean_title}.{ext}" if ext else os.path.basename(doc.file.name)

        safe_mime = get_safe_mime_type(doc.file.path)
        response = FileResponse(
            open(doc.file.path, 'rb'),
            as_attachment=True,
            filename=download_name,
            content_type=safe_mime,
        )
        return response


class DocumentPreviewView(FirmRequiredMixin, View):
    """
    Secure inline document preview handler for PDFs, images, and text files.
    Firm-scoped with strict client verification and audit logging.
    """
    def get(self, request, document_id):
        doc = get_firm_document_or_404(request, document_id)

        if not getattr(request.user, 'is_client_user', False):
            if not request.has_firm_perm('view_document'):
                raise PermissionDenied(_("You do not have permission to view documents."))

        if not doc.file or not os.path.exists(doc.file.path):
            raise Http404(_("Document file is missing on the server repository."))

        # Audit log preview
        log_audit(
            request=request,
            action=AuditLog.ActionType.VIEW,
            object_type='Document',
            object_id=str(doc.id),
            description=f"Previewed document '{doc.title}' for client {doc.client.display_business_name}.",
        )

        safe_mime = get_safe_mime_type(doc.file.path)
        # PDFs, images, and text can be served inline
        response = FileResponse(
            open(doc.file.path, 'rb'),
            as_attachment=False,
            content_type=safe_mime,
        )
        # Content disposition inline allows browser preview
        response['Content-Disposition'] = f'inline; filename="{slugify(doc.title)}.{doc.file_extension}"'
        return response


class DocumentEditView(PermissionRequiredMixin, View):
    """
    Rename document and update category, fiscal year, expiry, and description.
    """
    firm_permission = 'upload_document'

    def post(self, request, document_id):
        doc = get_firm_document_or_404(request, document_id)
        form = DocumentEditForm(request.POST, instance=doc)

        if not form.is_valid():
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _("Could not update document metadata. Please check inputs."))
            return redirect(request.POST.get('next') or reverse('documents:document_list'))

        updated_doc = form.save()

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Document',
            object_id=str(updated_doc.id),
            description=f"Updated document metadata and renamed to '{updated_doc.title}'.",
        )

        msg = _(f"Document '{updated_doc.title}' updated successfully.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg)})

        messages.success(request, msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list'))


class DocumentArchiveView(PermissionRequiredMixin, View):
    """
    Toggles document between ACTIVE and ARCHIVED status.
    """
    firm_permission = 'delete_document'

    def post(self, request, document_id):
        doc = get_firm_document_or_404(request, document_id)

        if doc.status == Document.Status.ARCHIVED:
            doc.status = Document.Status.ACTIVE
            doc.is_active = True
            action_desc = f"Restored document '{doc.title}' to active repository."
            user_msg = _(f"Document '{doc.title}' has been restored.")
        else:
            doc.status = Document.Status.ARCHIVED
            doc.is_active = False
            action_desc = f"Archived document '{doc.title}'."
            user_msg = _(f"Document '{doc.title}' has been archived.")

        doc.save(update_fields=['status', 'is_active', 'updated_at'])

        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='Document',
            object_id=str(doc.id),
            description=action_desc,
        )

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'status': doc.status, 'message': str(user_msg)})

        messages.success(request, user_msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list'))


class DocumentDeleteView(PermissionRequiredMixin, View):
    """
    Permanently deletes a document and cleans up disk storage.
    """
    firm_permission = 'delete_document'

    def post(self, request, document_id):
        doc = get_firm_document_or_404(request, document_id)
        doc_title = doc.title
        client_name = doc.client.display_business_name

        # Clean up file on disk if exists
        try:
            if doc.file and os.path.exists(doc.file.path):
                os.remove(doc.file.path)
        except Exception:
            pass

        doc.delete()

        log_audit(
            request=request,
            action=AuditLog.ActionType.DELETE,
            object_type='Document',
            object_id=str(document_id),
            description=f"Permanently deleted document '{doc_title}' from client {client_name}.",
        )

        msg = _(f"Document '{doc_title}' permanently deleted.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg)})

        messages.success(request, msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list'))


class DocumentRequestCreateView(PermissionRequiredMixin, View):
    """
    Staff creates a document request targeted at a client entity.
    """
    firm_permission = 'request_document'

    def post(self, request):
        firm = request.firm
        form = DocumentRequestForm(request.POST, firm=firm)

        if not form.is_valid():
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            messages.error(request, _("Could not create document request. Please check required fields."))
            return redirect(request.POST.get('next') or reverse('documents:document_list') + '?tab=requests')

        doc_req = form.save(commit=False)
        doc_req.firm = firm
        doc_req.requested_by = request.user
        doc_req.status = DocumentRequest.Status.REQUESTED
        doc_req.requested_date = timezone.localdate()
        doc_req.save()

        ClientActivity.objects.create(
            firm=firm,
            client=doc_req.client,
            activity_type=ClientActivity.ActivityType.DOC_REQUESTED,
            description=f"Requested documents: '{doc_req.requested_documents}' due by {doc_req.due_date}.",
            performed_by=request.user,
        )

        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='DocumentRequest',
            object_id=str(doc_req.id),
            description=f"Sent document request to {doc_req.client.display_business_name}: '{doc_req.requested_documents}' (Due: {doc_req.due_date}).",
        )

        msg = _(f"Document request sent to {doc_req.client.display_business_name}.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg), 'request_id': str(doc_req.id)})

        messages.success(request, msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list') + '?tab=requests')


class DocumentRequestUpdateStatusView(PermissionRequiredMixin, View):
    """
    Staff updates the status, deadline, or notes of a document request.
    """
    firm_permission = 'request_document'

    def post(self, request, request_id):
        doc_req = get_firm_document_request_or_404(request, request_id)
        new_status = request.POST.get('status', '').strip().upper()
        notes = request.POST.get('notes')

        if new_status and new_status in DocumentRequest.Status.values:
            old_status = doc_req.status
            doc_req.status = new_status
            if new_status == DocumentRequest.Status.RECEIVED and not doc_req.received_date:
                doc_req.received_date = timezone.now()
            if notes is not None:
                doc_req.notes = notes
            doc_req.save()

            log_audit(
                request=request,
                action=AuditLog.ActionType.UPDATE,
                object_type='DocumentRequest',
                object_id=str(doc_req.id),
                description=f"Updated status of document request '{doc_req.requested_documents}' from {old_status} to {new_status}.",
            )
            msg = _(f"Status updated to {doc_req.get_status_display()}.")
        else:
            msg = _("Invalid status specified.")

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg)})

        messages.success(request, msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list') + '?tab=requests')


class DocumentRequestDeleteView(PermissionRequiredMixin, View):
    """
    Deletes a document request.
    """
    firm_permission = 'request_document'

    def post(self, request, request_id):
        doc_req = get_firm_document_request_or_404(request, request_id)
        req_title = doc_req.requested_documents
        client_name = doc_req.client.display_business_name

        doc_req.delete()

        log_audit(
            request=request,
            action=AuditLog.ActionType.DELETE,
            object_type='DocumentRequest',
            object_id=str(request_id),
            description=f"Deleted document request '{req_title}' for client {client_name}.",
        )

        msg = _(f"Document request '{req_title}' deleted.")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg)})

        messages.success(request, msg)
        return redirect(request.POST.get('next') or reverse('documents:document_list') + '?tab=requests')


# ============================================================================
# CLIENT PORTAL DOCUMENT SYSTEM
# ============================================================================

class ClientPortalDocumentRequestsView(FirmRequiredMixin, View):
    """
    Client Portal View: Client sees requested documents sent by their CA firm,
    views statuses (Requested, Overdue, Received, etc.), and uploads submissions.
    """
    template_name = 'documents/portal_requests.html'

    def get(self, request):
        firm = request.firm
        user = request.user

        # Resolve the Client entity representing this user
        client = get_user_client(user, firm)
        if not client and not user.is_superuser:
            # If internal staff is previewing portal, pick first client in firm
            if not getattr(user, 'is_client_user', False):
                client = Client.objects.filter(firm=firm, is_active=True).first()

        if not client:
            return render(request, self.template_name, {
                'error_message': _("No associated client entity found for your portal account."),
                'client': None,
                'requests': [],
            })

        requests_qs = DocumentRequest.objects.filter(
            firm=firm,
            client=client,
        ).select_related('requested_by', 'uploaded_document').order_by('due_date', '-created_at')

        return render(request, self.template_name, {
            'client': client,
            'requests': requests_qs,
            'fulfill_form': ClientPortalFulfillRequestForm(),
            'breadcrumbs': [
                {'title': 'Client Portal', 'url': ''},
                {'title': 'Requested Documents', 'url': ''},
            ],
        })


class ClientPortalFulfillRequestView(FirmRequiredMixin, View):
    """
    Client portal submission endpoint: Uploads the requested file,
    links it to the DocumentRequest, updates status to RECEIVED, and logs audit.
    """
    def post(self, request, request_id):
        firm = request.firm
        doc_req = get_firm_document_request_or_404(request, request_id)
        form = ClientPortalFulfillRequestForm(request.POST, request.FILES)

        if not form.is_valid():
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            for errs in form.errors.values():
                for err in errs:
                    messages.error(request, err)
            return redirect('documents:portal_requests')

        uploaded_file = form.cleaned_data['file']
        client_notes = form.cleaned_data.get('notes', '')

        # 1. Create the Document repository entry
        doc = Document.objects.create(
            firm=firm,
            client=doc_req.client,
            title=f"Submission: {doc_req.requested_documents}",
            category=Document.Category.OTHER,
            fiscal_year=getattr(doc_req.client, 'fiscal_year', '2081/82') or '2081/82',
            file=uploaded_file,
            uploaded_by=request.user,
            description=client_notes,
            status=Document.Status.ACTIVE,
        )

        # 2. Update the DocumentRequest to RECEIVED
        doc_req.uploaded_document = doc
        doc_req.status = DocumentRequest.Status.RECEIVED
        doc_req.received_date = timezone.now()
        if client_notes:
            doc_req.notes = f"{doc_req.notes}\n[Client Note]: {client_notes}".strip()
        doc_req.save()

        # 3. Create client activity
        ClientActivity.objects.create(
            firm=firm,
            client=doc_req.client,
            activity_type=ClientActivity.ActivityType.DOC_UPLOADED,
            description=f"Client fulfilled request '{doc_req.requested_documents}' by uploading '{doc.title}'.",
            performed_by=request.user,
        )

        # 4. Audit Log
        log_audit(
            request=request,
            action=AuditLog.ActionType.CREATE,
            object_type='Document',
            object_id=str(doc.id),
            description=f"Client uploaded document '{doc.title}' via client portal.",
        )
        log_audit(
            request=request,
            action=AuditLog.ActionType.UPDATE,
            object_type='DocumentRequest',
            object_id=str(doc_req.id),
            description=f"Fulfilled document request '{doc_req.requested_documents}' for client {doc_req.client.display_business_name}.",
        )

        msg = _(f"Document successfully submitted for '{doc_req.requested_documents}'. Thank you!")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': str(msg), 'document_id': str(doc.id)})

        messages.success(request, msg)
        return redirect('documents:portal_requests')


class ClientPortalDocumentListView(FirmRequiredMixin, View):
    """
    Client views list of historical documents in their repository.
    """
    template_name = 'documents/portal_documents.html'

    def get(self, request):
        firm = request.firm
        user = request.user

        client = get_user_client(user, firm)
        if not client and not getattr(user, 'is_client_user', False):
            client = Client.objects.filter(firm=firm, is_active=True).first()

        if not client:
            return render(request, self.template_name, {
                'client': None,
                'documents': [],
                'error_message': _("No associated client entity found for your account."),
            })

        docs = Document.objects.filter(
            firm=firm,
            client=client,
            status=Document.Status.ACTIVE,
        ).order_by('-created_at')

        return render(request, self.template_name, {
            'client': client,
            'documents': docs,
            'breadcrumbs': [
                {'title': 'Client Portal', 'url': ''},
                {'title': 'Company Documents', 'url': ''},
            ],
        })
