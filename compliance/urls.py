from django.urls import path
from .views import ComplianceDeadlineListView

app_name = 'compliance'

urlpatterns = [
    path('', ComplianceDeadlineListView.as_view(), name='compliance_list'),
]
