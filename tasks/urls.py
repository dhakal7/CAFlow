from django.urls import path
from tasks.views import (
    TaskAttachDocumentView,
    TaskAssignView,
    TaskChecklistAddView,
    TaskChecklistDeleteView,
    TaskChecklistToggleView,
    TaskCommentCreateView,
    TaskCompleteView,
    TaskCreateView,
    TaskDeleteView,
    TaskDetailView,
    TaskEditView,
    TaskJsonView,
    TaskListView,
    TaskStatusUpdateView,
    WorkflowTemplateCreateView,
    WorkflowTemplateDeleteView,
    WorkflowTemplateListView,
)

app_name = 'tasks'

urlpatterns = [
    # Task Views
    path('', TaskListView.as_view(), name='task_list'),
    path('create/', TaskCreateView.as_view(), name='task_create'),
    path('<uuid:task_id>/', TaskDetailView.as_view(), name='task_detail'),
    path('<uuid:task_id>/json/', TaskJsonView.as_view(), name='task_json'),
    path('<uuid:task_id>/edit/', TaskEditView.as_view(), name='task_edit'),
    path('<uuid:task_id>/assign/', TaskAssignView.as_view(), name='task_assign'),
    path('<uuid:task_id>/status/', TaskStatusUpdateView.as_view(), name='task_status_update'),
    path('<uuid:task_id>/complete/', TaskCompleteView.as_view(), name='task_complete'),
    path('<uuid:task_id>/delete/', TaskDeleteView.as_view(), name='task_delete'),

    # Checklist Item Actions
    path('<uuid:task_id>/checklist/add/', TaskChecklistAddView.as_view(), name='task_checklist_add'),
    path('checklist/<uuid:item_id>/toggle/', TaskChecklistToggleView.as_view(), name='task_checklist_toggle'),
    path('checklist/<uuid:item_id>/delete/', TaskChecklistDeleteView.as_view(), name='task_checklist_delete'),

    # Attachments & Comments
    path('<uuid:task_id>/attach/', TaskAttachDocumentView.as_view(), name='task_attach_document'),
    path('<uuid:task_id>/comment/', TaskCommentCreateView.as_view(), name='task_comment_create'),

    # Workflow Templates
    path('templates/', WorkflowTemplateListView.as_view(), name='template_list'),
    path('templates/create/', WorkflowTemplateCreateView.as_view(), name='template_create'),
    path('templates/<uuid:template_id>/delete/', WorkflowTemplateDeleteView.as_view(), name='template_delete'),
]
