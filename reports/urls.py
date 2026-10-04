from django.urls import path
from .views import ReportDashboardView

app_name = 'reports'

urlpatterns = [
    path('', ReportDashboardView.as_view(), name='report_dashboard'),
]
