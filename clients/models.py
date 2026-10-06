from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import FirmAwareModel


class Client(FirmAwareModel):
    """
    Client Entity representing business entities, NGOs, or individuals served by the CA Firm.
    """
    class ClientType(models.TextChoices):
        PVT_LTD = 'PVT_LTD', _('Private Limited Company')
        PUB_LTD = 'PUB_LTD', _('Public Limited Company')
        PROPRIETORSHIP = 'PROPRIETORSHIP', _('Proprietorship Business')
        PARTNERSHIP = 'PARTNERSHIP', _('Partnership Firm')
        NGO_INGO = 'NGO_INGO', _('NGO / INGO / Non-Profit')
        INDIVIDUAL = 'INDIVIDUAL', _('Individual Taxpayer')

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        ONBOARDING = 'ONBOARDING', _('Onboarding')
        INACTIVE = 'INACTIVE', _('Inactive')
        SUSPENDED = 'SUSPENDED', _('Suspended')
        ARCHIVED = 'ARCHIVED', _('Archived')

    name = models.CharField(_('Client Name / Contact Person'), max_length=255)
    legal_name = models.CharField(
        _('Legal / Registered Name'),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_('Official registered legal entity name, e.g. ABC Pvt Ltd'),
    )
    business_name = models.CharField(
        _('Business / Trade Name'),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_('Registered entity or trade name, e.g. ABC Pvt Ltd'),
    )
    pan_number = models.CharField(
        _('IRD PAN Number'),
        max_length=15,
        blank=True,
        db_index=True,
        help_text=_('9-Digit Inland Revenue Department PAN Number'),
    )
    registration_number = models.CharField(
        _('Company Registrar (OCR) Reg No'),
        max_length=50,
        blank=True,
    )
    registration_date = models.DateField(
        _('Company Registration Date'),
        null=True,
        blank=True,
        help_text=_('Date of registration / incorporation'),
    )
    tax_registration_date = models.DateField(
        _('PAN / Tax Registration Date'),
        null=True,
        blank=True,
        help_text=_('Date of IRD PAN / VAT registration'),
    )
    important_dates = models.JSONField(
        _('Important Dates & Milestones'),
        default=dict,
        blank=True,
        help_text=_('Dictionary of key statutory and compliance milestone dates'),
    )
    notes = models.TextField(
        _('Internal Notes / Remarks'),
        blank=True,
        help_text=_('Internal practice notes, background info, or special handling remarks'),
    )
    client_type = models.CharField(
        _('Client Category'),
        max_length=30,
        choices=ClientType.choices,
        default=ClientType.PVT_LTD,
    )
    contact_person = models.CharField(_('Contact Person / Director'), max_length=200, blank=True)
    email = models.EmailField(_('Primary Email'), blank=True)
    phone = models.CharField(_('Official Phone / Mobile'), max_length=30, blank=True)
    address = models.CharField(_('Registered Address'), max_length=255, blank=True)
    city = models.CharField(_('City / District'), max_length=100, default='Kathmandu')
    fiscal_year = models.CharField(_('Fiscal Year'), max_length=20, default='2081/82', blank=True)
    services = models.JSONField(
        _('Subscribed CA Services'),
        default=list,
        blank=True,
        help_text=_('List of service keys active for this client'),
    )
    status = models.CharField(
        _('Client Status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    assigned_manager = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_clients',
        verbose_name=_('Engagement Lead / Manager'),
    )
    assigned_staff = models.ManyToManyField(
        'accounts.User',
        related_name='servicing_clients',
        blank=True,
        verbose_name=_('Assigned Engagement Staff'),
    )
    portal_user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_client_entities',
        verbose_name=_('Client Portal User Contact'),
        help_text=_('User account for external client portal access.'),
    )

    class Meta:
        verbose_name = _('Client')
        verbose_name_plural = _('Clients')
        ordering = ['name']

    def __str__(self):
        biz = self.display_business_name
        return f"{biz} (PAN: {self.pan_number or 'N/A'})"

    def clean(self):
        super().clean()
        if self.assigned_manager_id and self.firm_id:
            from firms.models import FirmMembership, MembershipStatus
            from django.core.exceptions import ValidationError
            is_member = FirmMembership.objects.filter(
                firm_id=self.firm_id,
                user_id=self.assigned_manager_id,
                status=MembershipStatus.ACTIVE,
                user__is_active=True,
            ).exists()
            if not is_member:
                raise ValidationError({'assigned_manager': _('Assigned manager must be an active member of this firm.')})

    def save(self, *args, **kwargs):
        if not self.business_name and self.legal_name:
            self.business_name = self.legal_name
        if not self.legal_name and self.business_name:
            self.legal_name = self.business_name
        if not self.name:
            self.name = self.legal_name or self.business_name or "Client"
        super().save(*args, **kwargs)

    @property
    def display_business_name(self):
        return self.business_name or self.legal_name or self.name

    @property
    def display_legal_name(self):
        return self.legal_name or self.business_name or self.name

    @property
    def display_contact_name(self):
        return self.contact_person or self.name

    @property
    def services_display(self):
        service_map = {
            'STATUTORY_AUDIT': 'Statutory Audit',
            'TAX_VAT': 'Tax & VAT',
            'BOOKKEEPING': 'Bookkeeping',
            'OCR_COMPLIANCE': 'OCR Filing',
            'INTERNAL_AUDIT': 'Internal Audit',
            'TDS_WITHHOLDING': 'TDS Advisory',
            'ADVISORY': 'Due Diligence',
        }
        if not self.services:
            return ['General CA']
        return [service_map.get(s, s) for s in self.services]

    def get_next_deadline(self):
        """Returns the nearest upcoming statutory compliance or task deadline."""
        from compliance.models import ComplianceDeadline
        from tasks.models import Task
        from django.utils import timezone
        today = timezone.localdate()

        comp = self.compliance_deadlines.filter(
            due_date_ad__gte=today
        ).exclude(status__in=['COMPLETED', 'FILED']).order_by('due_date_ad').first()

        task = self.tasks.filter(
            due_date__gte=today
        ).exclude(status=Task.Status.COMPLETED).order_by('due_date').first()

        if comp and task:
            if comp.due_date_ad <= task.due_date:
                days = (comp.due_date_ad - today).days
                return {
                    'title': comp.title,
                    'date': comp.due_date_ad,
                    'date_bs': comp.due_date_bs,
                    'days_left': days,
                    'is_urgent': days <= 3,
                    'type': 'compliance',
                }
            else:
                days = (task.due_date - today).days
                return {
                    'title': task.title,
                    'date': task.due_date,
                    'date_bs': '',
                    'days_left': days,
                    'is_urgent': days <= 3,
                    'type': 'task',
                }
        elif comp:
            days = (comp.due_date_ad - today).days
            return {
                'title': comp.title,
                'date': comp.due_date_ad,
                'date_bs': comp.due_date_bs,
                'days_left': days,
                'is_urgent': days <= 3,
                'type': 'compliance',
            }
        elif task:
            days = (task.due_date - today).days
            return {
                'title': task.title,
                'date': task.due_date,
                'date_bs': '',
                'days_left': days,
                'is_urgent': days <= 3,
                'type': 'task',
            }
        return None

    @property
    def status_badge_class(self):
        badges = {
            self.Status.ACTIVE: 'cf-badge-success',
            self.Status.ONBOARDING: 'cf-badge-warning',
            self.Status.INACTIVE: 'cf-badge-muted',
            self.Status.SUSPENDED: 'cf-badge-danger',
            self.Status.ARCHIVED: 'cf-badge-secondary',
        }
        return badges.get(self.status, 'cf-badge-secondary')

    def get_assigned_team_by_role(self):
        """
        Categorizes assigned team members into 4 standardized practice tiers:
        - CA (Engagement Lead / Partner)
        - Senior (Senior Associate)
        - Accountant (Accountant)
        - Staff (Staff Associate / Trainee)
        """
        from firms.models import FirmMembership, FirmRole, MembershipStatus

        team_members = set()
        if self.assigned_manager:
            team_members.add(self.assigned_manager)
        for s in self.assigned_staff.all():
            team_members.add(s)

        memberships = {
            m.user_id: m for m in FirmMembership.objects.filter(
                firm=self.firm,
                user__in=team_members,
                status=MembershipStatus.ACTIVE,
            ).select_related('user')
        }

        ca_list = []
        senior_list = []
        accountant_list = []
        staff_list = []

        for u in team_members:
            m = memberships.get(u.id)
            role = m.role if m else (FirmRole.CA if u == self.assigned_manager else FirmRole.STAFF)
            member_dict = {
                'id': str(u.id),
                'user': u,
                'name': u.get_full_name(),
                'email': u.email,
                'phone': u.phone,
                'role': role,
                'role_display': m.get_role_display() if m else 'Associate',
                'ican': u.ican_membership_no,
                'initials': (u.first_name[:1] + u.last_name[:1]) if u.first_name else 'CA',
                'is_lead': (u == self.assigned_manager),
            }
            if role in [FirmRole.CA, FirmRole.OWNER, FirmRole.ADMIN]:
                ca_list.append(member_dict)
            elif role == FirmRole.SENIOR:
                senior_list.append(member_dict)
            elif role == FirmRole.ACCOUNTANT:
                accountant_list.append(member_dict)
            elif role == FirmRole.STAFF:
                staff_list.append(member_dict)
            else:
                staff_list.append(member_dict)

        # Ensure manager is present in CA list if not already
        if self.assigned_manager and not any(m['id'] == str(self.assigned_manager.id) for m in ca_list):
            ca_list.insert(0, {
                'id': str(self.assigned_manager.id),
                'user': self.assigned_manager,
                'name': self.assigned_manager.get_full_name(),
                'email': self.assigned_manager.email,
                'phone': self.assigned_manager.phone,
                'role': 'CA',
                'role_display': 'Engagement Lead (CA)',
                'ican': self.assigned_manager.ican_membership_no,
                'initials': (self.assigned_manager.first_name[:1] + self.assigned_manager.last_name[:1]) if self.assigned_manager.first_name else 'CA',
                'is_lead': True,
            })

        return {
            'ca': ca_list,
            'senior': senior_list,
            'accountant': accountant_list,
            'staff': staff_list,
            'total_count': len(team_members),
            'has_team': bool(team_members),
        }



class ClientActivity(FirmAwareModel):
    """
    Immutable recent activity timeline entries for client interactions and audit events.
    """
    class ActivityType(models.TextChoices):
        NEW_CLIENT = 'NEW_CLIENT', _('New Client Onboarded')
        DOC_UPLOADED = 'DOC_UPLOADED', _('Document Uploaded')
        TASK_COMPLETED = 'TASK_COMPLETED', _('Task Completed')
        CORRECTION_REQUESTED = 'CORRECTION_REQUESTED', _('Correction Requested')
        INVOICE_PAID = 'INVOICE_PAID', _('Invoice Paid')
        MESSAGE_RECEIVED = 'MESSAGE_RECEIVED', _('Message Received')
        STAFF_ASSIGNED = 'STAFF_ASSIGNED', _('Staff Assigned')
        DOC_REQUESTED = 'DOC_REQUESTED', _('Document Requested')
        TASK_CREATED = 'TASK_CREATED', _('Task Created')
        STATUS_CHANGED = 'STATUS_CHANGED', _('Status Changed')
        CLIENT_ARCHIVED = 'CLIENT_ARCHIVED', _('Client Archived')
        CLIENT_RESTORED = 'CLIENT_RESTORED', _('Client Restored')

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='activities',
        null=True,
        blank=True,
        verbose_name=_('Client Entity'),
    )
    activity_type = models.CharField(
        _('Activity Type'),
        max_length=30,
        choices=ActivityType.choices,
        default=ActivityType.NEW_CLIENT,
        db_index=True,
    )
    description = models.CharField(_('Activity Description'), max_length=255)
    performed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_activities',
    )

    class Meta:
        verbose_name = _('Client Activity')
        verbose_name_plural = _('Client Activities')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.description}"

    def clean(self):
        super().clean()
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'client': _('Client must belong to the same firm as the activity.')})

    def save(self, *args, **kwargs):
        if self.client_id and self.firm_id and self.client.firm_id != self.firm_id:
            raise ValueError(_('Cannot attach a client from another firm to this activity.'))
        super().save(*args, **kwargs)

