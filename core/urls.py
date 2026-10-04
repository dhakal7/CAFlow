from django.urls import path
from .views import LandingPageView, DashboardView, DesignSystemView

app_name = 'core'

urlpatterns = [
    path('', LandingPageView.as_view(), name='landing'),
    path('workspace/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('design-system/', DesignSystemView.as_view(), name='design_system'),
]
