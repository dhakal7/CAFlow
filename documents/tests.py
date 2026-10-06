import os
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from clients.models import Client, ClientActivity
from documents.forms import DocumentUploadForm
from documents.models import Document, DocumentRequest
from documents.validators import validate_document_file, MAX_FILE_SIZE_BYTES
from firms.models import Firm, FirmMembership, FirmRole, MembershipStatus


class DocumentBaseTestCase(TestCase):
    """
    Base test case with two firms, multiple roles, and clients for cross-tenant isolation testing.
    """
    def setUp(self):
        # 1. Firm A (Dhakal & Associates)
        self.firm_a = Firm.objects.create(name='Dhakal & Associates', slug='dhakal-assoc')
        self.user_a_owner = User.objects.create_user('owner_a@dhakal.com', 'Pass12345!', first_name='Suyog', last_name='Dhakal')
        self.user_a_staff = User.objects.create_user('staff_a@dhakal.com', 'Pass12345!', first_name='Bikash', last_name='Karki')
        FirmMembership.objects.create(user=self.user_a_owner, firm=self.firm_a, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)
        FirmMembership.objects.create(user=self.user_a_staff, firm=self.firm_a, role=FirmRole.STAFF, status=MembershipStatus.ACTIVE)

        # 2. Firm B (Pokhara Tax Partners)
        self.firm_b = Firm.objects.create(name='Pokhara Tax Partners', slug='pokhara-tax')
        self.user_b_owner = User.objects.create_user('owner_b@pokhara.com', 'Pass12345!', first_name='Hari', last_name='Sharma')
        FirmMembership.objects.create(user=self.user_b_owner, firm=self.firm_b, role=FirmRole.OWNER, status=MembershipStatus.ACTIVE)

        # 3. Client for Firm A
        self.client_a = Client.objects.create(
            firm=self.firm_a,
            name='Ramesh Adhikari',
            business_name='Himalayan Traders Pvt Ltd',
            pan_number='601928374',
            client_type=Client.ClientType.PVT_LTD,
            email='ramesh@himalayan.com.np',
            status=Client.Status.ACTIVE,
            fiscal_year='2081/82',
        )

        # 4. Client for Firm B
        self.client_b = Client.objects.create(
            firm=self.firm_b,
            name='Sunil Thapa',
            business_name='Apex Hydropower Ltd',
            pan_number='300481920',
            client_type=Client.ClientType.PUB_LTD,
            email='sunil@apex.com.np',
            status=Client.Status.ACTIVE,
            fiscal_year='2081/82',
        )

        # 5. Client Portal User for Client A
        self.client_user_a = User.objects.create_user('client_user_a@himalayan.com.np', 'Pass12345!', first_name='Ramesh', last_name='Adhikari')
        FirmMembership.objects.create(user=self.client_user_a, firm=self.firm_a, role=FirmRole.CLIENT, status=MembershipStatus.ACTIVE)
        self.client_a.portal_user = self.client_user_a
        self.client_a.save()

        # Dummy file for tests
        self.sample_pdf = SimpleUploadedFile(
            "audit_report.pdf",
            b"%PDF-1.4 test audit report content",
            content_type="application/pdf"
        )
        self.sample_xlsx = SimpleUploadedFile(
            "vat_purchase.xlsx",
            b"fake excel content",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        self.http_client = HttpClient()


class DocumentModelTests(DocumentBaseTestCase):
    """Test Document and DocumentRequest model behaviors and validation."""

    def test_document_creation_and_auto_properties(self):
        doc = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='FY 2080/81 Final Audit Report',
            category=Document.Category.AUDIT_WORKING_PAPERS,
            fiscal_year='2080/81',
            file=self.sample_pdf,
            uploaded_by=self.user_a_owner,
            expiry_date=timezone.localdate() + timedelta(days=60),
            status=Document.Status.ACTIVE,
        )
        self.assertEqual(doc.file_extension, 'pdf')
        self.assertTrue(doc.can_preview)
        self.assertEqual(doc.preview_type, 'pdf')
        self.assertFalse(doc.is_expired)
        self.assertFalse(doc.is_expiring_soon)
        self.assertGreater(doc.file_size_bytes, 0)

    def test_expiry_date_properties(self):
        # Expired doc
        doc_expired = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Expired Tax Clearance',
            category=Document.Category.TAX_FILING,
            file=self.sample_pdf,
            expiry_date=timezone.localdate() - timedelta(days=5),
        )
        self.assertTrue(doc_expired.is_expired)
        self.assertFalse(doc_expired.is_expiring_soon)

        # Expiring soon doc (15 days away)
        doc_soon = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Expiring Agreement',
            category=Document.Category.LEGAL_CONTRACTS,
            file=self.sample_pdf,
            expiry_date=timezone.localdate() + timedelta(days=15),
        )
        self.assertFalse(doc_soon.is_expired)
        self.assertTrue(doc_soon.is_expiring_soon)

    def test_cross_firm_client_association_prevented(self):
        """A document cannot attach a client belonging to another firm."""
        doc = Document(
            firm=self.firm_a,
            client=self.client_b,  # Client B belongs to Firm B!
            title='Illegal Cross-Firm Doc',
            file=self.sample_pdf,
        )
        with self.assertRaises(ValidationError):
            doc.clean()
        with self.assertRaises(ValueError):
            doc.save()

    def test_document_request_model_and_cross_firm_prevention(self):
        doc_req = DocumentRequest.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            requested_documents='Bhadra Month Bank Statements & Ledger',
            due_date=timezone.localdate() + timedelta(days=7),
            status=DocumentRequest.Status.REQUESTED,
            requested_by=self.user_a_owner,
        )
        self.assertEqual(doc_req.status, DocumentRequest.Status.REQUESTED)
        self.assertFalse(doc_req.is_overdue)

        # Cross-firm validation
        cross_req = DocumentRequest(
            firm=self.firm_a,
            client=self.client_b,
            requested_documents='Illegal Request',
            due_date=timezone.localdate(),
        )
        with self.assertRaises(ValidationError):
            cross_req.clean()
        with self.assertRaises(ValueError):
            cross_req.save()

    def test_document_request_overdue_property(self):
        past_req = DocumentRequest.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            requested_documents='Past Audit Vouchers',
            due_date=timezone.localdate() - timedelta(days=3),
            status=DocumentRequest.Status.REQUESTED,
        )
        self.assertTrue(past_req.is_overdue)

        # If received, should not be considered overdue even if past due_date
        past_req.status = DocumentRequest.Status.RECEIVED
        self.assertFalse(past_req.is_overdue)


class DocumentValidationTests(DocumentBaseTestCase):
    """Test file validator: file types, prohibited extensions, and size limits."""

    def test_allowed_file_types(self):
        valid_files = [
            ("doc.pdf", b"%PDF", "application/pdf"),
            ("sheet.xlsx", b"data", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("photo.png", b"\x89PNG", "image/png"),
            ("notes.txt", b"plain text", "text/plain"),
            ("archive.zip", b"PK", "application/zip"),
        ]
        for fname, content, ctype in valid_files:
            f = SimpleUploadedFile(fname, content, content_type=ctype)
            self.assertEqual(validate_document_file(f), f)

    def test_prohibited_executable_extensions(self):
        prohibited = ["malicious.exe", "script.sh", "run.bat", "hack.php", "logic.py", "test.js"]
        for fname in prohibited:
            f = SimpleUploadedFile(fname, b"print('bad')", content_type="application/octet-stream")
            with self.assertRaises(ValidationError):
                validate_document_file(f)

    def test_oversized_file_rejected(self):
        large_file = SimpleUploadedFile(
            "big_file.pdf",
            b"0" * 100,
            content_type="application/pdf"
        )
        # Mock size to exceed 25 MB
        large_file.size = MAX_FILE_SIZE_BYTES + 1024
        with self.assertRaises(ValidationError) as ctx:
            validate_document_file(large_file)
        self.assertIn("exceeds the allowed limit", str(ctx.exception))


class DocumentSecurityAndAccessTests(DocumentBaseTestCase):
    """Test multi-tenant isolation, cross-firm protection, and permissions."""

    def setUp(self):
        super().setUp()
        # Create documents in Firm A and Firm B
        self.doc_a = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Confidential Working Paper A',
            category=Document.Category.AUDIT_WORKING_PAPERS,
            file=SimpleUploadedFile("firm_a_paper.pdf", b"Confidential A content"),
            uploaded_by=self.user_a_owner,
        )
        self.doc_b = Document.objects.create(
            firm=self.firm_b,
            client=self.client_b,
            title='Confidential Working Paper B',
            category=Document.Category.TAX_FILING,
            file=SimpleUploadedFile("firm_b_tax.pdf", b"Confidential B content"),
            uploaded_by=self.user_b_owner,
        )

    def test_cross_firm_download_blocked(self):
        """User from Firm A cannot download Firm B document by manipulating URL."""
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        url = reverse('documents:document_download', kwargs={'document_id': self.doc_b.id})
        response = self.http_client.get(url)
        # Should return 404 Not Found (or 403)
        self.assertEqual(response.status_code, 404)

    def test_cross_firm_preview_blocked(self):
        """User from Firm A cannot preview Firm B document."""
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        url = reverse('documents:document_preview', kwargs={'document_id': self.doc_b.id})
        response = self.http_client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_redirected(self):
        url = reverse('documents:document_list')
        response = self.http_client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_authorized_user_can_download_and_generates_audit_log(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        url = reverse('documents:document_download', kwargs={'document_id': self.doc_a.id})
        response = self.http_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response.headers.get('Content-Disposition', ''))

        # Check Audit Log recorded EXPORT
        audit_entry = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='Document',
            object_id=str(self.doc_a.id),
            action=AuditLog.ActionType.EXPORT,
        ).first()
        self.assertIsNotNone(audit_entry)

    def test_authorized_user_can_preview_and_generates_audit_log(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        url = reverse('documents:document_preview', kwargs={'document_id': self.doc_a.id})
        response = self.http_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('inline;', response.headers.get('Content-Disposition', ''))

        audit_entry = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='Document',
            object_id=str(self.doc_a.id),
            action=AuditLog.ActionType.VIEW,
        ).first()
        self.assertIsNotNone(audit_entry)

    def test_missing_physical_file_handled_gracefully(self):
        # Create document with missing physical file
        ghost_doc = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Ghost Document',
            file='firm_documents/non_existent_file.pdf',
        )
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        url = reverse('documents:document_download', kwargs={'document_id': ghost_doc.id})
        response = self.http_client.get(url)
        # Should gracefully redirect with error message, not crash 500!
        self.assertEqual(response.status_code, 302)


class DocumentCRUDAndAuditTests(DocumentBaseTestCase):
    """Test upload, edit, archive, restore, and delete operations."""

    def test_document_upload_success(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        upload_file = SimpleUploadedFile("tax_assessment_2080.pdf", b"Assessment order content")
        data = {
            'title': 'IRD Assessment Order FY 2080/81',
            'client': str(self.client_a.id),
            'category': Document.Category.TAX_FILING,
            'fiscal_year': '2080/81',
            'expiry_date': '',
            'description': 'Issued by Large Taxpayers Office',
            'file': upload_file,
        }
        url = reverse('documents:document_upload')
        response = self.http_client.post(url, data)
        self.assertEqual(response.status_code, 302)

        new_doc = Document.objects.filter(firm=self.firm_a, title='IRD Assessment Order FY 2080/81').first()
        self.assertIsNotNone(new_doc)
        self.assertEqual(new_doc.client, self.client_a)
        self.assertEqual(new_doc.uploaded_by, self.user_a_owner)
        self.assertEqual(new_doc.status, Document.Status.ACTIVE)

        # Audit Log CREATE
        audit_entry = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='Document',
            object_id=str(new_doc.id),
            action=AuditLog.ActionType.CREATE,
        ).first()
        self.assertIsNotNone(audit_entry)

        # ClientActivity created
        activity = ClientActivity.objects.filter(client=self.client_a, activity_type=ClientActivity.ActivityType.DOC_UPLOADED).first()
        self.assertIsNotNone(activity)

    def test_document_rename_and_metadata_update(self):
        doc = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Old Document Name',
            category=Document.Category.OTHER,
            fiscal_year='2081/82',
            file=self.sample_pdf,
        )
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        edit_url = reverse('documents:document_edit', kwargs={'document_id': doc.id})
        response = self.http_client.post(edit_url, {
            'title': 'Renamed Statutory Balance Sheet',
            'category': Document.Category.FINANCIAL_STATEMENTS,
            'fiscal_year': '2080/81',
            'status': 'ACTIVE',
            'expiry_date': '',
            'description': 'Updated description',
        })
        self.assertEqual(response.status_code, 302)

        doc.refresh_from_db()
        self.assertEqual(doc.title, 'Renamed Statutory Balance Sheet')
        self.assertEqual(doc.category, Document.Category.FINANCIAL_STATEMENTS)

        audit_entry = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='Document',
            object_id=str(doc.id),
            action=AuditLog.ActionType.UPDATE,
        ).first()
        self.assertIsNotNone(audit_entry)

    def test_document_archive_and_restore(self):
        doc = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Archive Test Document',
            file=self.sample_pdf,
            status=Document.Status.ACTIVE,
        )
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        archive_url = reverse('documents:document_archive', kwargs={'document_id': doc.id})

        # Archive
        self.http_client.post(archive_url)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.ARCHIVED)
        self.assertFalse(doc.is_active)

        # Restore
        self.http_client.post(archive_url)
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.ACTIVE)
        self.assertTrue(doc.is_active)

    def test_document_delete_removes_record_and_audits(self):
        doc = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='To Be Deleted',
            file=self.sample_pdf,
        )
        doc_id = str(doc.id)
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        delete_url = reverse('documents:document_delete', kwargs={'document_id': doc.id})
        response = self.http_client.post(delete_url)
        self.assertEqual(response.status_code, 302)

        self.assertFalse(Document.objects.filter(id=doc_id).exists())
        audit_entry = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='Document',
            object_id=doc_id,
            action=AuditLog.ActionType.DELETE,
        ).first()
        self.assertIsNotNone(audit_entry)


class DocumentRequestWorkflowTests(DocumentBaseTestCase):
    """Test staff requesting documents and updating statuses."""

    def test_staff_create_document_request(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        create_url = reverse('documents:request_create')
        due = timezone.localdate() + timedelta(days=10)
        data = {
            'client': str(self.client_a.id),
            'requested_documents': 'Monthly Sales Book (Ashwin 2081)',
            'due_date': str(due),
            'notes': 'Please provide signed stamped copy.',
        }
        response = self.http_client.post(create_url, data)
        self.assertEqual(response.status_code, 302)

        req = DocumentRequest.objects.filter(firm=self.firm_a, requested_documents='Monthly Sales Book (Ashwin 2081)').first()
        self.assertIsNotNone(req)
        self.assertEqual(req.client, self.client_a)
        self.assertEqual(req.status, DocumentRequest.Status.REQUESTED)

        # Audit Log CREATE
        audit_entry = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='DocumentRequest',
            object_id=str(req.id),
            action=AuditLog.ActionType.CREATE,
        ).first()
        self.assertIsNotNone(audit_entry)

    def test_update_request_status_and_delete(self):
        req = DocumentRequest.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            requested_documents='Loan Agreement Copy',
            due_date=timezone.localdate() + timedelta(days=5),
            status=DocumentRequest.Status.REQUESTED,
        )
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')

        # Update status to RECEIVED
        status_url = reverse('documents:request_update_status', kwargs={'request_id': req.id})
        response = self.http_client.post(status_url, {'status': 'RECEIVED', 'notes': 'Received via courier'})
        self.assertEqual(response.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, DocumentRequest.Status.RECEIVED)
        self.assertIsNotNone(req.received_date)

        # Delete request
        del_url = reverse('documents:request_delete', kwargs={'request_id': req.id})
        response = self.http_client.post(del_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DocumentRequest.objects.filter(id=req.id).exists())


class ClientPortalDocumentTests(DocumentBaseTestCase):
    """Test client role portal view, request fulfillment, and client data isolation."""

    def test_client_role_redirected_to_portal_from_vault(self):
        self.http_client.login(email='client_user_a@himalayan.com.np', password='Pass12345!')
        response = self.http_client.get(reverse('documents:document_list'))
        # Should redirect to documents:portal_requests
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('documents:portal_requests'), response.url)

    def test_client_portal_requests_view(self):
        req1 = DocumentRequest.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            requested_documents='Tax Clearance Certificate',
            due_date=timezone.localdate() + timedelta(days=7),
            status=DocumentRequest.Status.REQUESTED,
        )
        self.http_client.login(email='client_user_a@himalayan.com.np', password='Pass12345!')
        response = self.http_client.get(reverse('documents:portal_requests'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tax Clearance Certificate')

    def test_client_fulfills_document_request(self):
        req = DocumentRequest.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            requested_documents='Audited Balance Sheet 2080',
            due_date=timezone.localdate() + timedelta(days=5),
            status=DocumentRequest.Status.REQUESTED,
        )
        self.http_client.login(email='client_user_a@himalayan.com.np', password='Pass12345!')
        fulfill_url = reverse('documents:portal_fulfill_request', kwargs={'request_id': req.id})
        upload_doc = SimpleUploadedFile("balance_sheet_signed.pdf", b"Signed balance sheet PDF content")

        response = self.http_client.post(fulfill_url, {
            'file': upload_doc,
            'notes': 'Attached signed copy from directors meeting.',
        })
        self.assertEqual(response.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, DocumentRequest.Status.RECEIVED)
        self.assertIsNotNone(req.uploaded_document)
        self.assertIsNotNone(req.received_date)
        self.assertEqual(req.uploaded_document.client, self.client_a)

        # Audit logs recorded
        audit_create = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='Document',
            object_id=str(req.uploaded_document.id),
            action=AuditLog.ActionType.CREATE,
        ).first()
        self.assertIsNotNone(audit_create)

        audit_fulfill = AuditLog.objects.filter(
            firm=self.firm_a,
            object_type='DocumentRequest',
            object_id=str(req.id),
            action=AuditLog.ActionType.UPDATE,
        ).first()
        self.assertIsNotNone(audit_fulfill)

    def test_client_cannot_download_other_client_document(self):
        """A client user cannot download documents belonging to another client in the same firm."""
        other_client = Client.objects.create(
            firm=self.firm_a,
            name='Other Client Pvt Ltd',
            pan_number='999999999',
            status=Client.Status.ACTIVE,
        )
        secret_doc = Document.objects.create(
            firm=self.firm_a,
            client=other_client,
            title='Confidential Competitor File',
            file=SimpleUploadedFile("secret.pdf", b"Secret data"),
        )
        self.http_client.login(email='client_user_a@himalayan.com.np', password='Pass12345!')
        download_url = reverse('documents:document_download', kwargs={'document_id': secret_doc.id})
        response = self.http_client.get(download_url)
        # 403 Forbidden!
        self.assertEqual(response.status_code, 403)


class DocumentVaultSearchAndFilterTests(DocumentBaseTestCase):
    """Test search, filtering by category/client/fiscal year/status, and sorting."""

    def setUp(self):
        super().setUp()
        self.doc1 = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='VAT Purchase Book Bhadra',
            category=Document.Category.VAT_SALES_PURCHASE,
            fiscal_year='2081/82',
            file=self.sample_pdf,
            status=Document.Status.ACTIVE,
        )
        self.doc2 = Document.objects.create(
            firm=self.firm_a,
            client=self.client_a,
            title='Statutory Audit Report Ashoj',
            category=Document.Category.AUDIT_WORKING_PAPERS,
            fiscal_year='2080/81',
            file=self.sample_pdf,
            status=Document.Status.ARCHIVED,
        )

    def test_search_by_title(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        response = self.http_client.get(reverse('documents:document_list'), {'q': 'Purchase Book'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAT Purchase Book Bhadra')
        self.assertNotContains(response, 'Statutory Audit Report Ashoj')

    def test_filter_by_category(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        response = self.http_client.get(reverse('documents:document_list'), {'category': Document.Category.VAT_SALES_PURCHASE})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAT Purchase Book Bhadra')

    def test_filter_archived_documents(self):
        self.http_client.login(email='owner_a@dhakal.com', password='Pass12345!')
        response = self.http_client.get(reverse('documents:document_list'), {'tab': 'archived'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Statutory Audit Report Ashoj')
        self.assertNotContains(response, 'VAT Purchase Book Bhadra')
