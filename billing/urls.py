from django.urls import path
from .views import InvoiceListView

app_name = 'billing'

urlpatterns = [
    path('', InvoiceListView.as_view(), name='invoice_list'),
]
