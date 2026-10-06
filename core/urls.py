from django.urls import path
from .views import (
    LandingPageView,
    DashboardView,
    DesignSystemView,
    QuickAddClientView,
    QuickCreateTaskView,
    QuickRequestDocView,
    QuickCreateInvoiceView,
    QuickCompleteTaskView,
    QuickRemindDocView,
)

app_name = 'core'

urlpatterns = [
    path('', LandingPageView.as_view(), name='landing'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('workspace/dashboard/', DashboardView.as_view(), name='workspace_dashboard'),
    path('design-system/', DesignSystemView.as_view(), name='design_system'),
    
    # Quick action workflows
    path('dashboard/quick-action/add-client/', QuickAddClientView.as_view(), name='quick_add_client'),
    path('dashboard/quick-action/create-task/', QuickCreateTaskView.as_view(), name='quick_create_task'),
    path('dashboard/quick-action/request-documents/', QuickRequestDocView.as_view(), name='quick_request_documents'),
    path('dashboard/quick-action/create-invoice/', QuickCreateInvoiceView.as_view(), name='quick_create_invoice'),
    path('dashboard/quick-action/complete-task/<uuid:task_id>/', QuickCompleteTaskView.as_view(), name='quick_complete_task'),
    path('dashboard/quick-action/remind-document/<uuid:req_id>/', QuickRemindDocView.as_view(), name='quick_remind_document'),
]
