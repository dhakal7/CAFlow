from django.urls import path
from .views import TeamListView, FirmSettingsView

app_name = 'firms'

urlpatterns = [
    path('team/', TeamListView.as_view(), name='team_list'),
    path('settings/', FirmSettingsView.as_view(), name='firm_settings'),
]
