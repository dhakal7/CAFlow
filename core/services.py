import datetime
from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.db.models import Sum, Q, Count, Case, When, IntegerField

from accounts.models import User
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus
from clients.models import Client, ClientActivity
from tasks.models import Task
from compliance.models import ComplianceDeadline
from documents.models import DocumentRequest
from billing.models import Invoice
from audit.services import log_audit


def get_default_demo_firm():
    """Returns the default firm or creates a baseline firm if none exists."""
    firm = Firm.objects.first()
    if not firm:
        firm = Firm.objects.create(
            name="Dhakal & Associates",
            slug="dhakal-associates",
            firm_type=Firm.FirmType.PARTNERSHIP,
            ican_firm_reg_no="1420",
            pan_number="601928374",
            email="info@dhakalassociates.com.np",
            phone="+977-1-4422110",
            address="Putalisadak, Ward 28",
            city="Kathmandu",
            country="Nepal",
            current_fiscal_year="2081/82",
            currency="NPR",
        )
    return firm


def seed_dashboard_demo_data(firm=None, user=None):
    """
    Seeds production-grade demo data for CAFlow dashboard development.
    Ensures exact target statistics:
    - 128 Clients
    - 24 Pending Tasks
    - 8 Compliance Deadlines
    - NPR 45K Outstanding Invoices
    - Document Requests, Team Workload, and Client Activities
    """
    if not firm:
        firm = get_default_demo_firm()

    # 1. Ensure Team Members
    team_data = [
        {
            'email': 'suyog@dhakalassociates.com.np',
            'first_name': 'CA. Suyog',
            'last_name': 'Dhakal',
            'ican_membership_no': 'FCA-1420',
            'role': FirmRole.OWNER,
        },
        {
            'email': 'anjali@dhakalassociates.com.np',
            'first_name': 'CA. Anjali',
            'last_name': 'Sharma',
            'ican_membership_no': 'CA-3180',
            'role': FirmRole.CA,
        },
        {
            'email': 'pooja@dhakalassociates.com.np',
            'first_name': 'Pooja',
            'last_name': 'Regmi',
            'ican_membership_no': '',
            'role': FirmRole.SENIOR,
        },
        {
            'email': 'bikash@dhakalassociates.com.np',
            'first_name': 'Bikash',
            'last_name': 'Karki',
            'ican_membership_no': '',
            'role': FirmRole.STAFF,
        },
    ]

    users = {}
    for td in team_data:
        u, _ = User.objects.get_or_create(
            email=td['email'],
            defaults={
                'first_name': td['first_name'],
                'last_name': td['last_name'],
                'ican_membership_no': td['ican_membership_no'],
                'is_email_verified': True,
            }
        )
        if not u.has_usable_password():
            u.set_password('CAflow@1234')
            u.save()
        users[td['email']] = u

        FirmMembership.objects.get_or_create(
            firm=firm,
            user=u,
            defaults={
                'role': td['role'],
                'status': MembershipStatus.ACTIVE,
            }
        )

    primary_user = user or users.get('suyog@dhakalassociates.com.np') or User.objects.first()

    # 2. Ensure Clients (target 128 clients)
    current_clients_count = Client.objects.filter(firm=firm).count()
    key_clients = [
        ("Himalayan Traders Pvt Ltd", "601928374", Client.ClientType.PVT_LTD, "Ramesh Adhikari", "CA. Anjali Sharma"),
        ("Apex Hydropower Development Ltd", "300481920", Client.ClientType.PUB_LTD, "Er. Sunil Thapa", "CA. Suyog Dhakal"),
        ("Kathmandu Tech Solutions", "604928113", Client.ClientType.PVT_LTD, "Prerana Shrestha", "Pooja Regmi"),
        ("Lumbini Cement Industries", "301827491", Client.ClientType.PUB_LTD, "Binod Agrawal", "CA. Anjali Sharma"),
        ("Everest Organic Teas", "603819204", Client.ClientType.PVT_LTD, "Karma Sherpa", "Bikash Karki"),
        ("Shangri-La Hydro Energy Ltd", "302918475", Client.ClientType.PUB_LTD, "Surendra Shakya", "CA. Suyog Dhakal"),
        ("Shikhar Microfinance Ltd", "301128940", Client.ClientType.PUB_LTD, "Deepak Joshi", "CA. Anjali Sharma"),
        ("Pashupati Fabrics & Garments", "602391029", Client.ClientType.PVT_LTD, "Navin Khetan", "Pooja Regmi"),
    ]

    client_objects = []
    services_pool = [
        ['STATUTORY_AUDIT', 'TAX_VAT'],
        ['TAX_VAT', 'OCR_COMPLIANCE'],
        ['STATUTORY_AUDIT', 'INTERNAL_AUDIT', 'TAX_VAT'],
        ['BOOKKEEPING', 'TAX_VAT', 'TDS_WITHHOLDING'],
        ['STATUTORY_AUDIT', 'ADVISORY'],
    ]
    for idx, (name, pan, ctype, contact, mgr_name) in enumerate(key_clients):
        cl, _ = Client.objects.get_or_create(
            firm=firm,
            pan_number=pan,
            defaults={
                'name': contact,
                'business_name': name,
                'client_type': ctype,
                'contact_person': contact,
                'email': f"contact@{name.lower().split()[0]}.com.np",
                'phone': "+977-1-4200000",
                'city': 'Kathmandu',
                'fiscal_year': '2081/82',
                'services': services_pool[idx % len(services_pool)],
                'status': Client.Status.ACTIVE,
            }
        )
        if not cl.business_name:
            cl.business_name = name
            cl.services = services_pool[idx % len(services_pool)]
            cl.save()
        client_objects.append(cl)

    # Bulk create dummy clients to reach exactly 128 if needed
    needed_clients = 128 - Client.objects.filter(firm=firm).count()
    if needed_clients > 0:
        bulk_clients = []
        base_num = current_clients_count + 1
        for i in range(needed_clients):
            num = base_num + i
            pan_val = f"60{num:07d}"[:9]
            bulk_clients.append(
                Client(
                    firm=firm,
                    name=f"Director #{num}",
                    business_name=f"Nepal Enterprise #{num} Pvt Ltd",
                    pan_number=pan_val,
                    client_type=Client.ClientType.PVT_LTD,
                    contact_person=f"Director #{num}",
                    email=f"client{num}@nepalbiz.com.np",
                    city="Kathmandu" if num % 2 == 0 else "Pokhara",
                    fiscal_year='2081/82',
                    services=services_pool[i % len(services_pool)],
                    status=Client.Status.ACTIVE if i % 10 != 0 else (Client.Status.ONBOARDING if i % 5 == 0 else Client.Status.INACTIVE),
                )
            )
        Client.objects.bulk_create(bulk_clients)

    # Re-fetch sample clients
    himalayan = Client.objects.filter(firm=firm, pan_number="601928374").first() or client_objects[0]
    apex = Client.objects.filter(firm=firm, pan_number="300481920").first() or client_objects[1]
    ktm_tech = Client.objects.filter(firm=firm, pan_number="604928113").first() or client_objects[2]
    lumbini = Client.objects.filter(firm=firm, pan_number="301827491").first() or client_objects[3]
    everest = Client.objects.filter(firm=firm, pan_number="603819204").first() or client_objects[4]

    # 3. Ensure Tasks (target 24 pending tasks)
    pending_tasks_count = Task.objects.filter(firm=firm).exclude(status=Task.Status.COMPLETED).count()
    today = timezone.localdate()

    if pending_tasks_count < 24:
        tasks_to_create = [
            # Today's Work Tasks
            {
                'title': "Physical Stock Audit Verification",
                'description': "Year-end inventory count working papers and valuation reconciliation under NAS 2.",
                'client': himalayan,
                'assigned_to': users['bikash@dhakalassociates.com.np'],
                'priority': Task.Priority.URGENT,
                'status': Task.Status.IN_PROGRESS,
                'due_date': today,
            },
            {
                'title': "D-03 Tax Assessment Reconciliation",
                'description': "Income Tax Act Section 99 return verification and advance tax tax-credit matching.",
                'client': lumbini,
                'assigned_to': users['anjali@dhakalassociates.com.np'],
                'priority': Task.Priority.HIGH,
                'status': Task.Status.UNDER_REVIEW,
                'due_date': today,
            },
            {
                'title': "Monthly Sales & Purchase VAT Ledger",
                'description': "Annex 5 & Annex 6 upload preparation and IRD e-portal VAT reconciliation.",
                'client': ktm_tech,
                'assigned_to': users['pooja@dhakalassociates.com.np'],
                'priority': Task.Priority.MEDIUM,
                'status': Task.Status.TODO,
                'due_date': today,
            },
            {
                'title': "NFRS Balance Sheet Working Papers",
                'description': "Depreciation schedules and fixed assets capitalization register review.",
                'client': apex,
                'assigned_to': users['suyog@dhakalassociates.com.np'],
                'priority': Task.Priority.HIGH,
                'status': Task.Status.IN_PROGRESS,
                'due_date': today + datetime.timedelta(days=1),
            },
            {
                'title': "Withholding Tax (TDS) Certificate Verification",
                'description': "E-TDS ledger matching with IRD Annexures for Q1 interest and contractor payments.",
                'client': everest,
                'assigned_to': users['bikash@dhakalassociates.com.np'],
                'priority': Task.Priority.MEDIUM,
                'status': Task.Status.TODO,
                'due_date': today + datetime.timedelta(days=2),
            },
        ]

        # Additional tasks to reach 24 pending tasks
        needed_tasks = 24 - pending_tasks_count
        created_count = 0
        for t_info in tasks_to_create:
            if not Task.objects.filter(firm=firm, title=t_info['title']).exists():
                Task.objects.create(firm=firm, **t_info)
                created_count += 1

        # Fill remainder up to 24
        current_pending = Task.objects.filter(firm=firm).exclude(status=Task.Status.COMPLETED).count()
        remainder = 24 - current_pending
        all_clients = list(Client.objects.filter(firm=firm)[:10])
        staff_list = list(users.values())

        for idx in range(remainder):
            cl = all_clients[idx % len(all_clients)]
            st = staff_list[idx % len(staff_list)]
            p_choices = [Task.Priority.URGENT, Task.Priority.HIGH, Task.Priority.MEDIUM, Task.Priority.LOW]
            s_choices = [Task.Status.TODO, Task.Status.IN_PROGRESS, Task.Status.UNDER_REVIEW]
            Task.objects.create(
                firm=firm,
                title=f"Statutory Audit Checklist Item #{idx + 6}",
                description="Routine accounting review and compliance documentation check.",
                client=cl,
                assigned_to=st,
                priority=p_choices[idx % len(p_choices)],
                status=s_choices[idx % len(s_choices)],
                due_date=today + datetime.timedelta(days=(idx % 7)),
            )

        # Also ensure some completed tasks for workload metrics
        if Task.objects.filter(firm=firm, status=Task.Status.COMPLETED).count() < 18:
            for idx in range(18):
                cl = all_clients[idx % len(all_clients)]
                st = staff_list[idx % len(staff_list)]
                Task.objects.create(
                    firm=firm,
                    title=f"Completed Working Paper FY 2081/82 #{idx + 1}",
                    description="Finalized statutory file signed by engagement manager.",
                    client=cl,
                    assigned_to=st,
                    priority=Task.Priority.MEDIUM,
                    status=Task.Status.COMPLETED,
                    due_date=today - datetime.timedelta(days=(idx + 1)),
                    completed_at=timezone.now() - datetime.timedelta(days=(idx + 1)),
                )

    # 4. Ensure Compliance Deadlines (target 8 due items)
    compliance_items = [
        {
            'title': "Monthly VAT Return (Bhadra)",
            'governing_act': ComplianceDeadline.GoverningAct.VAT,
            'client': himalayan,
            'due_date_bs': "2081-06-25",
            'due_date_ad': today + datetime.timedelta(days=3),
            'status': ComplianceDeadline.Status.DUE_SOON,
            'notes': "Inland Revenue Department • Section 17 of Value Added Tax Act 2052. 5 clients pending filing.",
            'assigned_to': users['bikash@dhakalassociates.com.np'],
        },
        {
            'title': "TDS Bi-monthly E-Return",
            'governing_act': ComplianceDeadline.GoverningAct.INCOME_TAX,
            'client': ktm_tech,
            'due_date_bs': "2081-06-25",
            'due_date_ad': today + datetime.timedelta(days=3),
            'status': ComplianceDeadline.Status.DUE_SOON,
            'notes': "Income Tax Act 2058 • Section 90. Withholding payments verification for Ashoj e-filing.",
            'assigned_to': users['pooja@dhakalassociates.com.np'],
        },
        {
            'title': "Company Registrar (OCR) D-01 Return",
            'governing_act': ComplianceDeadline.GoverningAct.COMPANIES_ACT,
            'client': apex,
            'due_date_bs': "2081-09-29",
            'due_date_ad': today + datetime.timedelta(days=45),
            'status': ComplianceDeadline.Status.UPCOMING,
            'notes': "Companies Act 2063 • Section 51. Annual General Meeting (AGM) notice and director list upload.",
            'assigned_to': users['anjali@dhakalassociates.com.np'],
        },
        {
            'title': "Advance Income Tax Installment (Q1 40%)",
            'governing_act': ComplianceDeadline.GoverningAct.INCOME_TAX,
            'client': lumbini,
            'due_date_bs': "2081-09-30",
            'due_date_ad': today + datetime.timedelta(days=46),
            'status': ComplianceDeadline.Status.UPCOMING,
            'notes': "Income Tax Act 2058 • Section 94. First installment computation on estimated turnover.",
            'assigned_to': users['suyog@dhakalassociates.com.np'],
        },
        {
            'title': "Social Security Fund (SSF) Monthly Contribution",
            'governing_act': ComplianceDeadline.GoverningAct.LABOUR_ACT,
            'client': himalayan,
            'due_date_bs': "2081-06-30",
            'due_date_ad': today + datetime.timedelta(days=7),
            'status': ComplianceDeadline.Status.DUE_SOON,
            'notes': "Labour Act 2074 & SSF Rules. Monthly 31% payroll contribution deposit.",
            'assigned_to': users['pooja@dhakalassociates.com.np'],
        },
        {
            'title': "Excise Duty Monthly Return Filing",
            'governing_act': ComplianceDeadline.GoverningAct.OTHER,
            'client': everest,
            'due_date_bs': "2081-06-25",
            'due_date_ad': today + datetime.timedelta(days=3),
            'status': ComplianceDeadline.Status.DUE_SOON,
            'notes': "Excise Act 2058. Factory dispatch registers and stamp verification.",
            'assigned_to': users['bikash@dhakalassociates.com.np'],
        },
        {
            'title': "Audited Financial Statements Filing (OCR D-03)",
            'governing_act': ComplianceDeadline.GoverningAct.COMPANIES_ACT,
            'client': apex,
            'due_date_bs': "2081-09-30",
            'due_date_ad': today + datetime.timedelta(days=46),
            'status': ComplianceDeadline.Status.UPCOMING,
            'notes': "Companies Act 2063 • Section 80. Auditor report and balance sheet submission.",
            'assigned_to': users['anjali@dhakalassociates.com.np'],
        },
        {
            'title': "ICAN Practice Peer Review Compliance",
            'governing_act': ComplianceDeadline.GoverningAct.ICAN_ACT,
            'client': None,
            'due_date_bs': "2081-07-15",
            'due_date_ad': today + datetime.timedelta(days=22),
            'status': ComplianceDeadline.Status.UPCOMING,
            'notes': "Nepal Chartered Accountants Act 2053. Quality Assurance Board audit sample file compilation.",
            'assigned_to': users['suyog@dhakalassociates.com.np'],
        },
    ]

    for c_info in compliance_items:
        if not ComplianceDeadline.objects.filter(firm=firm, title=c_info['title']).exists():
            ComplianceDeadline.objects.create(firm=firm, **c_info)

    # 5. Ensure Invoices (target NPR 45K outstanding across 4 invoices)
    if Invoice.objects.filter(firm=firm).exclude(status=Invoice.Status.PAID).count() < 4:
        invoice_items = [
            {
                'invoice_number': "2081-041",
                'client': himalayan,
                'subtotal_npr': Decimal('13274.34'),
                'vat_percent': Decimal('13.00'),
                'vat_amount_npr': Decimal('1725.66'),
                'total_amount_npr': Decimal('15000.00'),
                'paid_amount_npr': Decimal('0.00'),
                'status': Invoice.Status.ISSUED,
                'issue_date': today - datetime.timedelta(days=12),
                'due_date': today + datetime.timedelta(days=5),
            },
            {
                'invoice_number': "2081-042",
                'client': ktm_tech,
                'subtotal_npr': Decimal('10619.47'),
                'vat_percent': Decimal('13.00'),
                'vat_amount_npr': Decimal('1380.53'),
                'total_amount_npr': Decimal('12000.00'),
                'paid_amount_npr': Decimal('0.00'),
                'status': Invoice.Status.ISSUED,
                'issue_date': today - datetime.timedelta(days=8),
                'due_date': today + datetime.timedelta(days=7),
            },
            {
                'invoice_number': "2081-043",
                'client': lumbini,
                'subtotal_npr': Decimal('8849.56'),
                'vat_percent': Decimal('13.00'),
                'vat_amount_npr': Decimal('1150.44'),
                'total_amount_npr': Decimal('10000.00'),
                'paid_amount_npr': Decimal('0.00'),
                'status': Invoice.Status.ISSUED,
                'issue_date': today - datetime.timedelta(days=5),
                'due_date': today + datetime.timedelta(days=10),
            },
            {
                'invoice_number': "2081-044",
                'client': everest,
                'subtotal_npr': Decimal('7079.65'),
                'vat_percent': Decimal('13.00'),
                'vat_amount_npr': Decimal('920.35'),
                'total_amount_npr': Decimal('8000.00'),
                'paid_amount_npr': Decimal('0.00'),
                'status': Invoice.Status.ISSUED,
                'issue_date': today - datetime.timedelta(days=2),
                'due_date': today + datetime.timedelta(days=12),
            },
        ]
        for inv_info in invoice_items:
            if not Invoice.objects.filter(firm=firm, invoice_number=inv_info['invoice_number']).exists():
                Invoice.objects.create(firm=firm, **inv_info)

    # 6. Ensure Document Requests
    if DocumentRequest.objects.filter(firm=firm).count() < 4:
        doc_requests = [
            {
                'client': apex,
                'requested_documents': "Bank Confirmation Letter (Nabil Bank & Global IME)",
                'due_date': today - datetime.timedelta(days=2),
                'status': DocumentRequest.Status.OVERDUE,
                'notes': "Required for year-end independent bank balance verification.",
                'requested_by': users['suyog@dhakalassociates.com.np'],
            },
            {
                'client': himalayan,
                'requested_documents': "Bhadra Month Sales & Purchase Invoices (Annex 5)",
                'due_date': today + datetime.timedelta(days=2),
                'status': DocumentRequest.Status.PENDING,
                'notes': "14 voucher scanned batches needed before 24th Ashoj VAT filing.",
                'requested_by': users['bikash@dhakalassociates.com.np'],
            },
            {
                'client': lumbini,
                'requested_documents': "Signed Board Minutes of 15th AGM & Dividend Approval",
                'due_date': today + datetime.timedelta(days=5),
                'status': DocumentRequest.Status.PENDING,
                'notes': "Required for OCR filing and audit report finalization.",
                'requested_by': users['anjali@dhakalassociates.com.np'],
            },
            {
                'client': ktm_tech,
                'requested_documents': "Fixed Asset Physical Verification Register FY 2080/81",
                'due_date': today + datetime.timedelta(days=8),
                'status': DocumentRequest.Status.RECEIVED,
                'notes': "Depreciation schedules and asset tag confirmation received.",
                'requested_by': users['pooja@dhakalassociates.com.np'],
            },
        ]
        for dr in doc_requests:
            DocumentRequest.objects.get_or_create(
                firm=firm,
                client=dr['client'],
                requested_documents=dr['requested_documents'],
                defaults=dr,
            )

    # 7. Ensure Recent Client Activities covering all 6 types
    if ClientActivity.objects.filter(firm=firm).count() < 6:
        activities = [
            {
                'activity_type': ClientActivity.ActivityType.TASK_COMPLETED,
                'client': apex,
                'description': "CA. Suyog Dhakal signed off on Apex Hydro Audit working papers",
                'performed_by': users['suyog@dhakalassociates.com.np'],
            },
            {
                'activity_type': ClientActivity.ActivityType.DOC_UPLOADED,
                'client': himalayan,
                'description': "Himalayan Traders uploaded Bhadra Purchase Register (Annex 5)",
                'performed_by': users['bikash@dhakalassociates.com.np'],
            },
            {
                'activity_type': ClientActivity.ActivityType.NEW_CLIENT,
                'client': Client.objects.filter(firm=firm, pan_number="302918475").first() or apex,
                'description': "Shangri-La Hydro Energy Ltd onboarded as new corporate client",
                'performed_by': users['anjali@dhakalassociates.com.np'],
            },
            {
                'activity_type': ClientActivity.ActivityType.INVOICE_PAID,
                'client': lumbini,
                'description': "Lumbini Cement cleared invoice INV-2081-040 (NPR 35,000 via NCHL)",
                'performed_by': users['pooja@dhakalassociates.com.np'],
            },
            {
                'activity_type': ClientActivity.ActivityType.CORRECTION_REQUESTED,
                'client': ktm_tech,
                'description': "Correction requested for Kathmandu Tech TDS ledger reconciliation",
                'performed_by': users['pooja@dhakalassociates.com.np'],
            },
            {
                'activity_type': ClientActivity.ActivityType.MESSAGE_RECEIVED,
                'client': everest,
                'description': "Everest Organic Teas sent query regarding OCR AGM resolution deadline",
                'performed_by': users['bikash@dhakalassociates.com.np'],
            },
        ]
        for act in activities:
            ClientActivity.objects.create(firm=firm, **act)

    return firm


def get_dashboard_data(firm=None, user=None, search_query=None, status_filter=None, priority_filter=None, task_scope=None):
    """
    Retrieves and aggregates all dashboard data for the active firm from Django models.
    Strictly tenant-scoped to the provided firm.
    Includes real task metrics: pending, overdue, due today, completed, assigned to me.
    """
    if not firm:
        raise ValueError("Active firm workspace is required to load dashboard data.")

    today = timezone.localdate()
    three_days_later = today + datetime.timedelta(days=3)

    # 1. Real Task Counts by CA Workflow Metrics
    task_counts = {
        'pending': Task.objects.filter(firm=firm).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]).count(),
        'overdue': Task.objects.filter(firm=firm, due_date__lt=today).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]).count(),
        'due_today': Task.objects.filter(firm=firm, due_date=today).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]).count(),
        'completed': Task.objects.filter(firm=firm, status=Task.Status.COMPLETED).count(),
        'assigned_to_me': Task.objects.filter(firm=firm, assigned_to=user).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED]).count() if user else 0,
    }

    # Stat Cards Calculations
    total_clients_count = Client.objects.filter(firm=firm).count()
    active_clients_count = Client.objects.filter(firm=firm, status=Client.Status.ACTIVE).count()
    pending_tasks_count = task_counts['pending']
    under_review_tasks_count = Task.objects.filter(firm=firm, status=Task.Status.UNDER_REVIEW).count()

    # Compliance due soon count (statutory filings)
    compliance_due_soon_count = ComplianceDeadline.objects.filter(
        firm=firm,
    ).exclude(status__in=[ComplianceDeadline.Status.COMPLETED, ComplianceDeadline.Status.FILED, ComplianceDeadline.Status.CANCELLED]).count()

    # Nearest upcoming compliance for stat card
    nearest_compliance = ComplianceDeadline.objects.filter(
        firm=firm,
        due_date_ad__gte=today,
    ).exclude(status__in=[ComplianceDeadline.Status.COMPLETED, ComplianceDeadline.Status.FILED, ComplianceDeadline.Status.CANCELLED]).order_by('due_date_ad').first()

    if nearest_compliance:
        days_left = (nearest_compliance.due_date_ad - today).days
        comp_trend = f"{days_left} Days" if days_left > 0 else ("Today" if days_left == 0 else "Overdue")
        comp_trend_variant = 'danger' if days_left <= 3 else 'warning'
        comp_supporting = nearest_compliance.title
    elif compliance_due_soon_count > 0:
        comp_trend = f"{compliance_due_soon_count} Pending"
        comp_trend_variant = 'warning'
        comp_supporting = "Statutory filings pending"
    else:
        comp_trend = "All Current"
        comp_trend_variant = "success"
        comp_supporting = "No pending statutory filings"

    # Outstanding invoices sum
    unpaid_invoices = Invoice.objects.filter(
        firm=firm,
        status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL, Invoice.Status.DRAFT]
    )
    unpaid_count = unpaid_invoices.count()
    agg_result = unpaid_invoices.aggregate(
        total=Sum('total_amount_npr') - Sum('paid_amount_npr')
    )
    total_outstanding_npr = agg_result['total'] if agg_result['total'] is not None else Decimal('0.00')

    # Format outstanding amount
    if total_outstanding_npr >= 1000:
        formatted_outstanding = f"NPR {int(total_outstanding_npr / 1000)}K"
    else:
        formatted_outstanding = f"NPR {total_outstanding_npr:,.0f}"

    task_supporting = f"{task_counts['overdue']} Overdue • {task_counts['due_today']} Due Today" if (task_counts['overdue'] > 0 or task_counts['due_today'] > 0) else ('Awaiting partner signoff' if under_review_tasks_count > 0 else 'All workflows active')

    stat_cards = {
        'total_clients': {
            'label': 'Total Clients',
            'value': str(total_clients_count),
            'trend': f"{active_clients_count} Active" if total_clients_count > 0 else "0 Active",
            'trend_positive': True,
            'supporting_text': f"FY {firm.current_fiscal_year}",
            'icon': 'users',
        },
        'pending_tasks': {
            'label': 'Pending Tasks',
            'value': str(pending_tasks_count),
            'trend': f"{under_review_tasks_count} Review",
            'trend_variant': 'warning',
            'supporting_text': task_supporting,
            'icon': 'clipboard',
        },
        'due_soon': {
            'label': 'Due Soon',
            'value': str(compliance_due_soon_count),
            'trend': comp_trend,
            'trend_variant': comp_trend_variant,
            'supporting_text': comp_supporting,
            'icon': 'alert-triangle',
        },
        'outstanding': {
            'label': 'Outstanding',
            'value': formatted_outstanding,
            'trend': f"{unpaid_count} Invoices",
            'trend_variant': 'primary',
            'supporting_text': 'Billed with 13% Nepal VAT',
            'icon': 'receipt',
        },
    }

    # 2. Today's Work Tasks (Pending engagements first, then due date)
    tasks_qs = Task.objects.filter(firm=firm).select_related('client', 'assigned_to')

    # Apply task scope filter if selected
    if task_scope == 'due_today':
        tasks_qs = tasks_qs.filter(due_date=today).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    elif task_scope == 'overdue':
        tasks_qs = tasks_qs.filter(due_date__lt=today).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    elif task_scope == 'assigned_to_me' and user:
        tasks_qs = tasks_qs.filter(assigned_to=user).exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])
    elif task_scope == 'completed':
        tasks_qs = tasks_qs.filter(status=Task.Status.COMPLETED)
    elif task_scope == 'pending':
        tasks_qs = tasks_qs.exclude(status__in=[Task.Status.COMPLETED, Task.Status.CANCELLED])

    tasks_qs = tasks_qs.order_by(
        models.Case(
            models.When(status=Task.Status.COMPLETED, then=1),
            default=0,
            output_field=models.IntegerField(),
        ),
        'due_date',
        '-priority',
    )

    # Apply search filter
    if search_query:
        tasks_qs = tasks_qs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(client__name__icontains=search_query) |
            Q(client__pan_number__icontains=search_query) |
            Q(assigned_to__first_name__icontains=search_query) |
            Q(assigned_to__last_name__icontains=search_query)
        )

    # Apply status filter
    if status_filter and status_filter != 'ALL':
        tasks_qs = tasks_qs.filter(status=status_filter)

    # Apply priority filter
    if priority_filter and priority_filter != 'ALL':
        tasks_qs = tasks_qs.filter(priority=priority_filter)

    todays_tasks = list(tasks_qs[:10])
    total_active_tasks_count = Task.objects.filter(firm=firm).exclude(status=Task.Status.COMPLETED).count()

    # 3. Upcoming Compliance
    compliance_items = list(ComplianceDeadline.objects.filter(firm=firm).select_related('client', 'assigned_to').order_by('due_date_ad')[:6])

    # 4. Document Requests
    document_requests = list(DocumentRequest.objects.filter(firm=firm).select_related('client', 'requested_by').order_by('due_date', '-created_at')[:5])

    # 5. Team Workload
    memberships = FirmMembership.objects.filter(firm=firm, status=MembershipStatus.ACTIVE).select_related('user').order_by('joined_at')
    team_workload = []

    for m in memberships:
        staff_user = m.user
        staff_tasks = Task.objects.filter(firm=firm, assigned_to=staff_user)
        active_count = staff_tasks.exclude(status=Task.Status.COMPLETED).count()
        completed_count = staff_tasks.filter(status=Task.Status.COMPLETED).count()
        total_staff_tasks = active_count + completed_count

        due_soon_count = staff_tasks.exclude(status=Task.Status.COMPLETED).filter(
            due_date__lte=three_days_later,
            due_date__gte=today,
        ).count()

        overdue_count = staff_tasks.exclude(status=Task.Status.COMPLETED).filter(
            due_date__lt=today
        ).count()

        # Completion percentage
        completion_pct = int((completed_count / total_staff_tasks) * 100) if total_staff_tasks > 0 else 0

        # Visual workload capacity level
        if active_count >= 8:
            capacity_level = 'danger'
            capacity_pct = min(100, int((active_count / 10) * 100))
            capacity_label = f"{capacity_pct}% Heavy Load"
        elif active_count >= 4:
            capacity_level = 'warning'
            capacity_pct = int((active_count / 10) * 100)
            capacity_label = f"{capacity_pct}% Active"
        elif active_count > 0:
            capacity_level = 'success'
            capacity_pct = int((active_count / 10) * 100)
            capacity_label = f"{capacity_pct}% Optimal"
        else:
            capacity_level = 'muted'
            capacity_pct = 0
            capacity_label = "Available"

        team_workload.append({
            'user': staff_user,
            'name': staff_user.get_full_name() or staff_user.email,
            'role': m.get_role_display(),
            'avatar_initials': (staff_user.first_name[:1] + staff_user.last_name[:1]).upper() if staff_user.first_name else 'CA',
            'active_tasks': active_count,
            'due_soon': due_soon_count,
            'overdue': overdue_count,
            'completion_pct': completion_pct,
            'capacity_pct': capacity_pct,
            'capacity_level': capacity_level,
            'capacity_label': capacity_label,
        })

    # 6. Recent Client Activity
    activities = list(ClientActivity.objects.filter(firm=firm).select_related('client', 'performed_by').order_by('-created_at')[:8])

    # 7. Lists for Quick Action Modals
    active_clients = list(Client.objects.filter(firm=firm, status=Client.Status.ACTIVE).order_by('name')[:30])
    active_staff = [m.user for m in memberships]

    return {
        'firm': firm,
        'stat_cards': stat_cards,
        'todays_tasks': todays_tasks,
        'total_active_tasks_count': total_active_tasks_count,
        'compliance_items': compliance_items,
        'document_requests': document_requests,
        'team_workload': team_workload,
        'recent_activities': activities,
        'active_clients': active_clients,
        'active_staff': active_staff,
        'search_query': search_query or '',
        'status_filter': status_filter or 'ALL',
        'priority_filter': priority_filter or 'ALL',
        'task_counts': task_counts,
        'task_scope': task_scope or 'all',
    }
