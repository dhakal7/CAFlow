from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from calendar_app.models import CalendarEvent
from compliance.models import ComplianceDeadline
from firms.mixins import FirmRequiredMixin


class CalendarView(FirmRequiredMixin, TemplateView):
    """
    Practice Calendar integrating physical audit visits, tax hearings, and statutory compliance deadlines.
    Strictly scoped to active firm workspace.
    """
    template_name = 'calendar_app/calendar.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not getattr(request, 'firm', None):
            return super().dispatch(request, *args, **kwargs)
        if not getattr(request, 'has_any_firm_perm', lambda p: False)(['view_task', 'view_compliance']):
            raise PermissionDenied(_("You do not have permission to access the practice calendar."))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        firm = self.request.firm
        today = timezone.localdate()

        # 1. Practice Events
        events = CalendarEvent.objects.filter(firm=firm).select_related('client', 'created_by').order_by('start_time')

        # 2. Statutory Compliance Deadlines
        deadlines = ComplianceDeadline.objects.filter(firm=firm).select_related(
            'client', 'assigned_to', 'compliance_type'
        ).order_by('due_date_ad')

        # Unified Calendar Items
        calendar_entries = []

        for d in deadlines:
            days_left = (d.due_date_ad - today).days
            calendar_entries.append({
                'id': str(d.id),
                'item_type': 'COMPLIANCE',
                'category_class': 'cal-tax-deadline',
                'title': d.title,
                'client_name': d.client.name if d.client else 'General Firm Statutory Filing',
                'date_ad': d.due_date_ad,
                'date_bs': d.due_date_bs,
                'status': d.status,
                'status_display': d.get_status_display(),
                'priority': d.priority,
                'days_left': days_left,
                'is_overdue': d.is_overdue,
                'notes': d.notes or d.description or 'Mandatory statutory return under Nepal Acts.',
                'assigned_to': d.assigned_to.get_full_name() if d.assigned_to else 'Unassigned',
                'url': f"/compliance/?id={d.id}",
            })

        for e in events:
            date_ad = e.start_time.date()
            days_left = (date_ad - today).days
            if e.event_type == CalendarEvent.EventType.AUDIT_VISIT:
                cls_name = 'cal-audit-visit'
            elif e.event_type == CalendarEvent.EventType.IRD_HEARING:
                cls_name = 'cal-ird-hearing'
            else:
                cls_name = 'cal-client-meeting'

            calendar_entries.append({
                'id': str(e.id),
                'item_type': e.event_type,
                'category_class': cls_name,
                'title': e.title,
                'client_name': e.client.name if e.client else 'Practice Event',
                'date_ad': date_ad,
                'date_bs': '',
                'status': 'SCHEDULED',
                'status_display': e.get_event_type_display(),
                'priority': 'MEDIUM',
                'days_left': days_left,
                'is_overdue': False,
                'notes': e.description,
                'assigned_to': e.created_by.get_full_name() if e.created_by else 'Team',
                'url': '#',
            })

        calendar_entries.sort(key=lambda x: x['date_ad'])

        context['breadcrumbs'] = [{'title': 'Calendar', 'url': ''}]
        context['calendar_entries'] = calendar_entries
        context['statutory_deadlines_count'] = deadlines.exclude(status__in=[
            ComplianceDeadline.Status.COMPLETED,
            ComplianceDeadline.Status.FILED,
            ComplianceDeadline.Status.CANCELLED
        ]).count()
        context['events_count'] = events.count()
        context['today'] = today
        return context
