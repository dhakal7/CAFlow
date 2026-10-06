import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus
from clients.models import Client, ClientActivity
from tasks.models import Task
from documents.models import Document, DocumentRequest
from compliance.models import ComplianceDeadline
from billing.models import Invoice
from messages_app.models import Conversation, ChatMessage


class Command(BaseCommand):
    help = "Seeds rich real data for Client Detail pages (documents, compliance, invoices, messages, tasks, activities, team assignments)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding comprehensive Client Detail data..."))
        firm = Firm.objects.first()
        if not firm:
            self.stdout.write(self.style.ERROR("No firm found."))
            return

        # 1. Ensure all 4 practice team roles exist in Dhakal & Associates
        suyog = User.objects.filter(email='suyog@dhakalassociates.com.np').first()
        anjali = User.objects.filter(email='anjali@dhakalassociates.com.np').first()
        pooja = User.objects.filter(email='pooja@dhakalassociates.com.np').first()
        bikash = User.objects.filter(email='bikash@dhakalassociates.com.np').first()

        ramesh, _ = User.objects.get_or_create(
            email='ramesh@dhakalassociates.com.np',
            defaults={
                'first_name': 'Ramesh',
                'last_name': 'Shrestha',
                'phone': '+977-9841392810',
                'is_email_verified': True,
            }
        )
        FirmMembership.objects.get_or_create(
            firm=firm,
            user=ramesh,
            defaults={'role': FirmRole.ACCOUNTANT, 'status': MembershipStatus.ACTIVE}
        )

        today = timezone.localdate()

        # Let's seed top clients
        clients = Client.objects.filter(firm=firm)[:10]

        dummy_pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Title (CAFlow Nepal Official Document) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

        doc_templates = [
            ("FY 2080/81 Audited Balance Sheet & P&L", Document.Category.FINANCIAL_STATEMENTS, "2080/81", 412000),
            ("Monthly VAT Purchase & Sales Ledger (Ashoj 2081)", Document.Category.VAT_SALES_PURCHASE, "2081/82", 185000),
            ("OCR Annual Return Form 21 & Minutes", Document.Category.COMPANY_REGISTRAR, "2080/81", 320000),
            ("IRD Advance Tax 1st Installment Computation", Document.Category.TAX_FILING, "2081/82", 145000),
            ("ICAN Statutory Audit Working Papers (NFRS)", Document.Category.AUDIT_WORKING_PAPERS, "2080/81", 890000),
            ("Shareholders Agreement & Memorandum Amendments", Document.Category.LEGAL_CONTRACTS, "2080/81", 540000),
        ]

        compliance_templates = [
            ("Monthly VAT Return & E-Filing (Ashoj 2081)", ComplianceDeadline.GoverningAct.VAT, "2081-07-25", today + timedelta(days=2), ComplianceDeadline.Status.DUE_SOON, "Mandatory under Section 19 of VAT Act 2052. 0.1% per day penalty on overdue returns."),
            ("First Advance Income Tax (40% of Estimated Liability)", ComplianceDeadline.GoverningAct.INCOME_TAX, "2081-09-30", today + timedelta(days=18), ComplianceDeadline.Status.UPCOMING, "Section 94 of Income Tax Act 2058. Interest levied at 15% p.a. under Section 118 for shortfall."),
            ("Company Registrar (OCR) Annual Returns & Auditor Appointment", ComplianceDeadline.GoverningAct.COMPANIES_ACT, "2081-09-15", today + timedelta(days=12), ComplianceDeadline.Status.IN_PROGRESS, "Filing of audited accounts & auditor appointment notice within 6 months of fiscal year close."),
            ("Bi-Annual Withholding Tax (E-TDS) Verification", ComplianceDeadline.GoverningAct.INCOME_TAX, "2081-10-15", today + timedelta(days=35), ComplianceDeadline.Status.UPCOMING, "Verification of e-TDS ledger against IRD portal submissions under Section 90."),
            ("Social Security Fund (SSF) Monthly Contribution", ComplianceDeadline.GoverningAct.LABOUR_ACT, "2081-07-30", today + timedelta(days=7), ComplianceDeadline.Status.UPCOMING, "Contribution of 31% (20% Employer + 11% Employee) under Labour Act & SSF Rules."),
        ]

        task_templates = [
            ("Audit Working Paper Verification: Fixed Assets & Depreciation", "Conduct physical asset verification sample and cross-check NFRS depreciation rates against Income Tax Act Schedule 2 block ceilings.", Task.Priority.HIGH, today + timedelta(days=4), Task.Status.IN_PROGRESS),
            ("Review Bank Reconciliation & Loan Covenants", "Inspect year-end bank confirmation letters and verify debt-service coverage ratio (DSCR) for consortium bank loans.", Task.Priority.MEDIUM, today + timedelta(days=8), Task.Status.TODO),
            ("Finalize Tax Computation & Deferred Tax Assets (NAS 12)", "Calculate permanent vs timing differences and establish deferred tax asset/liability reconciliations.", Task.Priority.URGENT, today + timedelta(days=3), Task.Status.UNDER_REVIEW),
            ("Verify VAT Debit Note / Credit Note Adjustments", "Cross-verify invoice cancellations and purchase returns against IRD central billing server (CBMS) logs.", Task.Priority.MEDIUM, today + timedelta(days=14), Task.Status.TODO),
            ("Obtain Director Representation Letter & ICAN Engagement Renewal", "Procure formal management representation signed by Managing Director per ICAN Standard on Auditing 580.", Task.Priority.LOW, today - timedelta(days=2), Task.Status.COMPLETED),
        ]

        invoice_templates = [
            ("2081-012", Decimal("60000.00"), Decimal("7800.00"), Decimal("67800.00"), Decimal("67800.00"), Invoice.Status.PAID, today - timedelta(days=30), today - timedelta(days=15)),
            ("2081-024", Decimal("45000.00"), Decimal("5850.00"), Decimal("50850.00"), Decimal("25000.00"), Invoice.Status.PARTIAL, today - timedelta(days=12), today + timedelta(days=3)),
            ("2081-039", Decimal("35000.00"), Decimal("4550.00"), Decimal("39550.00"), Decimal("0.00"), Invoice.Status.ISSUED, today - timedelta(days=5), today + timedelta(days=10)),
        ]

        conversation_topics = [
            (
                "FY 2080/81 Final Audit Report & Annexure 7 Queries",
                [
                    (anjali, "Namaste, we have reviewed your draft profit & loss statements. Please provide supporting vouchers for foreign consultancy expenses under Annexure 7 to verify withholding tax compliance."),
                    (suyog, "Also ensure that the TDS deposit voucher for US dollar remittances is attached with the bank realization certificate before tomorrow's review."),
                ]
            ),
            (
                "IRD VAT Audit Notice & Purchase Ledger Verification",
                [
                    (pooja, "We have prepared the reconciliation between CBMS sales records and your physical invoice books. Total difference is within 0.05%."),
                    (bikash, "All input tax credit invoices exceeding NPR 10,000 have been verified with supplier IRD active PAN status."),
                ]
            )
        ]

        for client in clients:
            # 1. Assign Team with all 4 roles: CA, Senior, Accountant, Staff
            client.assigned_manager = anjali or suyog
            client.save()
            client.assigned_staff.clear()
            for u in [suyog, pooja, ramesh, bikash]:
                if u:
                    client.assigned_staff.add(u)

            # Ensure client has multiple services
            if not client.services or len(client.services) < 3:
                client.services = ['STATUTORY_AUDIT', 'TAX_VAT', 'OCR_COMPLIANCE', 'BOOKKEEPING', 'TDS_WITHHOLDING']
                client.save(update_fields=['services'])

            # 2. Documents
            if client.documents.count() < 3:
                for idx, (title, cat, fy, size) in enumerate(doc_templates):
                    filename = f"sample_doc_{client.id}_{idx}.pdf"
                    doc = Document(
                        firm=firm,
                        client=client,
                        title=f"{title} - {client.display_business_name}",
                        category=cat,
                        fiscal_year=fy,
                        uploaded_by=anjali or suyog,
                        file_size_bytes=size,
                    )
                    doc.file.save(filename, ContentFile(dummy_pdf_content), save=True)

            # 3. Document Requests
            if client.document_requests.count() < 2:
                DocumentRequest.objects.create(
                    firm=firm,
                    client=client,
                    requested_documents="Q1 Bank Statement (Sanima Bank & Nabil Bank) & Loan Sanction Letters",
                    due_date=today + timedelta(days=5),
                    status=DocumentRequest.Status.PENDING,
                    requested_by=pooja or anjali,
                    notes="Please ensure bank statements bear official branch verification stamps or digitally signed e-statements.",
                )
                DocumentRequest.objects.create(
                    firm=firm,
                    client=client,
                    requested_documents="TDS Withholding Slips (15% Royalty & 1.5% Contract Withholding)",
                    due_date=today + timedelta(days=10),
                    status=DocumentRequest.Status.REMINDED,
                    requested_by=ramesh or anjali,
                    notes="Submit IRD payment vouchers for withholding tax deposited under head 11111.",
                )

            # 4. Compliance Deadlines
            if client.compliance_deadlines.count() < 3:
                for title, act, bs, ad, status, notes in compliance_templates:
                    ComplianceDeadline.objects.create(
                        firm=firm,
                        client=client,
                        title=f"{title} ({client.display_business_name})",
                        governing_act=act,
                        due_date_bs=bs,
                        due_date_ad=ad,
                        status=status,
                        notes=notes,
                        assigned_to=pooja or bikash or anjali,
                    )

            # 5. Tasks
            if client.tasks.count() < 4:
                for idx, (title, desc, prio, due, stat) in enumerate(task_templates):
                    assignee = [anjali, pooja, ramesh, bikash, suyog][idx % 5]
                    Task.objects.create(
                        firm=firm,
                        client=client,
                        title=f"{title}: {client.display_business_name}",
                        description=desc,
                        assigned_to=assignee,
                        priority=prio,
                        status=stat,
                        due_date=due,
                        completed_at=timezone.now() if stat == Task.Status.COMPLETED else None,
                    )

            # 6. Invoices
            if client.invoices.count() < 2:
                for serial, sub, vat, tot, paid, stat, iss, due in invoice_templates:
                    Invoice.objects.create(
                        firm=firm,
                        client=client,
                        invoice_number=f"{serial}-{str(client.id)[:4].upper()}",
                        subtotal_npr=sub,
                        vat_percent=Decimal("13.00"),
                        vat_amount_npr=vat,
                        total_amount_npr=tot,
                        paid_amount_npr=paid,
                        status=stat,
                        issue_date=iss,
                        due_date=due,
                    )

            # 7. Conversations & Messages
            if client.conversations.count() < 1:
                for c_title, msgs in conversation_topics:
                    conv = Conversation.objects.create(
                        firm=firm,
                        client=client,
                        title=f"{c_title} - {client.display_business_name}",
                    )
                    conv.participants.add(suyog, anjali, pooja, ramesh, bikash)
                    for sender, body in msgs:
                        ChatMessage.objects.create(
                            firm=firm,
                            conversation=conv,
                            sender=sender or suyog,
                            body=body,
                        )

            # 8. Activities
            if client.activities.count() < 5:
                ClientActivity.objects.create(
                    firm=firm,
                    client=client,
                    activity_type=ClientActivity.ActivityType.NEW_CLIENT,
                    description=f"Client '{client.display_business_name}' successfully registered and onboarded with PAN {client.pan_number or 'N/A'}.",
                    performed_by=suyog,
                    created_at=timezone.now() - timedelta(days=25),
                )
                ClientActivity.objects.create(
                    firm=firm,
                    client=client,
                    activity_type=ClientActivity.ActivityType.STAFF_ASSIGNED,
                    description=f"Assigned CA. Anjali Sharma as Lead CA and associate audit team (Pooja Regmi, Ramesh Shrestha, Bikash Karki).",
                    performed_by=suyog,
                    created_at=timezone.now() - timedelta(days=20),
                )
                ClientActivity.objects.create(
                    firm=firm,
                    client=client,
                    activity_type=ClientActivity.ActivityType.DOC_UPLOADED,
                    description=f"Uploaded FY 2080/81 Audited Balance Sheet & P&L report for statutory audit review.",
                    performed_by=anjali,
                    created_at=timezone.now() - timedelta(days=12),
                )
                ClientActivity.objects.create(
                    firm=firm,
                    client=client,
                    activity_type=ClientActivity.ActivityType.TASK_COMPLETED,
                    description=f"Completed task: 'Obtain Director Representation Letter & ICAN Engagement Renewal'.",
                    performed_by=pooja,
                    created_at=timezone.now() - timedelta(days=5),
                )
                ClientActivity.objects.create(
                    firm=firm,
                    client=client,
                    activity_type=ClientActivity.ActivityType.MESSAGE_RECEIVED,
                    description=f"Exchanged clarification regarding TDS withholding deductions under Annexure 7.",
                    performed_by=anjali,
                    created_at=timezone.now() - timedelta(days=2),
                )
                ClientActivity.objects.create(
                    firm=firm,
                    client=client,
                    activity_type=ClientActivity.ActivityType.STATUS_CHANGED,
                    description=f"Verified client compliance standing. Active statutory engagement confirmed.",
                    performed_by=suyog,
                    created_at=timezone.now() - timedelta(days=1),
                )

        self.stdout.write(self.style.SUCCESS("Successfully seeded rich Client Detail data!"))
