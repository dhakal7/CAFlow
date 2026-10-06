from django.contrib import admin
from compliance.models import (
    ComplianceDeadline,
    ComplianceType,
    ClientComplianceRequirement,
    ComplianceActivity,
)


@admin.register(ComplianceType)
class ComplianceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'frequency', 'statutory_authority', 'is_active', 'firm')
    list_filter = ('category', 'frequency', 'is_active', 'firm')
    search_fields = ('name', 'code', 'statutory_authority')


@admin.register(ComplianceDeadline)
class ComplianceDeadlineAdmin(admin.ModelAdmin):
    list_display = ('title', 'client', 'governing_act', 'due_date_bs', 'due_date_ad', 'status', 'priority', 'assigned_to', 'reviewer', 'firm')
    list_filter = ('status', 'governing_act', 'priority', 'is_recurring', 'firm')
    search_fields = ('title', 'client__name', 'filing_reference_number', 'notes')


@admin.register(ClientComplianceRequirement)
class ClientComplianceRequirementAdmin(admin.ModelAdmin):
    list_display = ('client', 'compliance_type', 'frequency', 'assigned_staff', 'is_active', 'firm')
    list_filter = ('frequency', 'is_active', 'firm')
    search_fields = ('client__name', 'compliance_type__name')


@admin.register(ComplianceActivity)
class ComplianceActivityAdmin(admin.ModelAdmin):
    list_display = ('deadline', 'action', 'from_status', 'to_status', 'performed_by', 'created_at', 'firm')
    list_filter = ('action', 'firm')
    search_fields = ('deadline__title', 'description')
