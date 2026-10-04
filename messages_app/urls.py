from django.urls import path
from .views import InboxView

app_name = 'messages_app'

urlpatterns = [
    path('', InboxView.as_view(), name='inbox'),
]
