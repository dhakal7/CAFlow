from django.urls import path
from .views import (
    ComplianceDeadlineListView,
    ComplianceDeadlineCreateView,
    ComplianceDeadlineDetailView,
    ComplianceDeadlineUpdateView,
    ComplianceDeadlineDeleteView,
    ComplianceStatusUpdateView,
    ComplianceLinkTaskView,
    ComplianceLinkDocumentView,
    ComplianceTypeManageView,
    ClientRequirementManageView,
    GenerateClientDeadlinesView,
    CheckOverdueDeadlinesView,
)

app_name = 'compliance'

urlpatterns = [
    path('', ComplianceDeadlineListView.as_view(), name='compliance_list'),
    path('create/', ComplianceDeadlineCreateView.as_view(), name='compliance_create'),
    path('<uuid:deadline_id>/', ComplianceDeadlineDetailView.as_view(), name='compliance_detail'),
    path('<uuid:deadline_id>/update/', ComplianceDeadlineUpdateView.as_view(), name='compliance_update'),
    path('<uuid:deadline_id>/delete/', ComplianceDeadlineDeleteView.as_view(), name='compliance_delete'),
    path('<uuid:deadline_id>/status/', ComplianceStatusUpdateView.as_view(), name='compliance_status_update'),
    path('<uuid:deadline_id>/link-task/', ComplianceLinkTaskView.as_view(), name='compliance_link_task'),
    path('<uuid:deadline_id>/link-document/', ComplianceLinkDocumentView.as_view(), name='compliance_link_document'),
    path('types/', ComplianceTypeManageView.as_view(), name='compliance_types'),
    path('requirements/add/', ClientRequirementManageView.as_view(), name='client_requirement_add'),
    path('generate-schedule/', GenerateClientDeadlinesView.as_view(), name='generate_schedule'),
    path('check-overdue/', CheckOverdueDeadlinesView.as_view(), name='check_overdue'),
]
