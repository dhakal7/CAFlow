from django.urls import path
from .views import TaskListView

app_name = 'tasks'

urlpatterns = [
    path('', TaskListView.as_view(), name='task_list'),
]
