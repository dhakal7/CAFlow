from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Document Vault Core
    path('', views.DocumentListView.as_view(), name='document_list'),
    path('upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('<uuid:document_id>/download/', views.DocumentDownloadView.as_view(), name='document_download'),
    path('<uuid:document_id>/preview/', views.DocumentPreviewView.as_view(), name='document_preview'),
    path('<uuid:document_id>/edit/', views.DocumentEditView.as_view(), name='document_edit'),
    path('<uuid:document_id>/archive/', views.DocumentArchiveView.as_view(), name='document_archive'),
    path('<uuid:document_id>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),

    # Document Requests Tracking
    path('requests/', views.DocumentRequestsListView.as_view(), name='request_list'),
    path('requests/create/', views.DocumentRequestCreateView.as_view(), name='request_create'),
    path('requests/<uuid:request_id>/status/', views.DocumentRequestUpdateStatusView.as_view(), name='request_update_status'),
    path('requests/<uuid:request_id>/delete/', views.DocumentRequestDeleteView.as_view(), name='request_delete'),

    # Client Portal
    path('portal/requests/', views.ClientPortalDocumentRequestsView.as_view(), name='portal_requests'),
    path('portal/requests/<uuid:request_id>/fulfill/', views.ClientPortalFulfillRequestView.as_view(), name='portal_fulfill_request'),
    path('portal/documents/', views.ClientPortalDocumentListView.as_view(), name='portal_documents'),
]
