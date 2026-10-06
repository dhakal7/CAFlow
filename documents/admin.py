from django.contrib import admin
from .models import Document, DocumentRequest


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'category', 'fiscal_year', 'status', 'file_size_bytes', 'created_at', 'firm')
    list_filter = ('category', 'status', 'fiscal_year', 'firm')
    search_fields = ('title', 'client__name', 'client__business_name')
    readonly_fields = ('created_at', 'updated_at', 'file_size_bytes', 'file_type')


@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = ('requested_documents', 'client', 'due_date', 'status', 'requested_by', 'firm')
    list_filter = ('status', 'firm')
    search_fields = ('requested_documents', 'client__name')
    readonly_fields = ('created_at', 'updated_at', 'received_date')
