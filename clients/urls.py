from django.urls import path
from .views import ClientListView

app_name = 'clients'

urlpatterns = [
    path('', ClientListView.as_view(), name='client_list'),
]
