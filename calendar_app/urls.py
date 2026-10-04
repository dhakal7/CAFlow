from django.urls import path
from .views import CalendarView

app_name = 'calendar_app'

urlpatterns = [
    path('', CalendarView.as_view(), name='calendar_view'),
]
