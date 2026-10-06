from django.urls import path
from .views import (
    ClientListView,
    ClientDetailView,
    ClientDetailJsonView,
    ClientCreateView,
    ClientEditView,
    ClientAssignStaffView,
    ClientRequestDocumentView,
    ClientCreateTaskView,
    ClientSendMessageView,
    ClientToggleStatusView,
    ClientArchiveView,
    ClientRestoreView,
    ClientCreateCalendarEventView,
    ClientUploadDocumentView,
    ClientCreateInvoiceView,
    ClientTaskToggleView,
    ClientExportView,
    ClientExportSingleView,
)

app_name = 'clients'

urlpatterns = [
    path('', ClientListView.as_view(), name='client_list'),
    path('create/', ClientCreateView.as_view(), name='client_create'),
    path('export/', ClientExportView.as_view(), name='client_export'),
    path('<uuid:client_id>/', ClientDetailView.as_view(), name='client_detail'),
    path('<uuid:client_id>/detail/', ClientDetailJsonView.as_view(), name='client_detail_json'),
    path('<uuid:client_id>/edit/', ClientEditView.as_view(), name='client_edit'),
    path('<uuid:client_id>/assign/', ClientAssignStaffView.as_view(), name='client_assign_staff'),
    path('<uuid:client_id>/request-document/', ClientRequestDocumentView.as_view(), name='client_request_document'),
    path('<uuid:client_id>/create-task/', ClientCreateTaskView.as_view(), name='client_create_task'),
    path('<uuid:client_id>/create-event/', ClientCreateCalendarEventView.as_view(), name='client_create_event'),
    path('<uuid:client_id>/send-message/', ClientSendMessageView.as_view(), name='client_send_message'),
    path('<uuid:client_id>/deactivate/', ClientToggleStatusView.as_view(), name='client_deactivate'),
    path('<uuid:client_id>/toggle-status/', ClientToggleStatusView.as_view(), name='client_toggle_status'),
    path('<uuid:client_id>/archive/', ClientArchiveView.as_view(), name='client_archive'),
    path('<uuid:client_id>/restore/', ClientRestoreView.as_view(), name='client_restore'),
    path('<uuid:client_id>/upload-document/', ClientUploadDocumentView.as_view(), name='client_upload_document'),
    path('<uuid:client_id>/create-invoice/', ClientCreateInvoiceView.as_view(), name='client_create_invoice'),
    path('<uuid:client_id>/tasks/<uuid:task_id>/toggle/', ClientTaskToggleView.as_view(), name='client_task_toggle'),
    path('<uuid:client_id>/export-dossier/', ClientExportSingleView.as_view(), name='client_export_single'),
]

