from odoo.tests.common import TransactionCase

REPORT = 'stockguard.report_warehouse_approval_request'


class TestApprovalRequestReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Ceftriaxone 1g',
            'type': 'product',
            'tracking': 'lot',
        })
        cls.lot = cls.env['stock.lot'].create({
            'name': 'CEF-2026-009',
            'product_id': cls.product.id,
            'company_id': cls.env.company.id,
        })
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.requester = Users.create({
            'name': 'Report Requester',
            'login': 'sg_report_requester',
            'groups_id': [(6, 0, [cls.env.ref('stockguard.group_warehouse_user').id])],
        })
        cls.approver = Users.create({
            'name': 'Report Approver',
            'login': 'sg_report_approver',
            'groups_id': [(6, 0, [
                cls.env.ref('stockguard.group_warehouse_approver').id,
                cls.env.ref('stock.group_stock_user').id,
            ])],
        })
        cls.request = cls.env['warehouse.approval.request'].create({
            'lot_id': cls.lot.id,
            'quantity': 75.0,
            'request_type': 'quality_override',
            'reason': 'Stability data reviewed and accepted by QA.',
            'requested_by_id': cls.requester.id,
            'approval_line_ids': [
                (0, 0, {'level': 1, 'approver_id': cls.approver.id}),
            ],
        })

    def _render_html(self, records):
        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            REPORT, records.ids
        )
        return html.decode()

    def test_report_action_is_bound_to_the_request_model(self):
        report = self.env.ref('stockguard.action_report_warehouse_approval_request')
        self.assertEqual(report.model, 'warehouse.approval.request')
        self.assertEqual(report.report_type, 'qweb-pdf')
        self.assertEqual(report.binding_model_id.model, 'warehouse.approval.request')

    def test_report_shows_the_request_details(self):
        html = self._render_html(self.request)
        self.assertIn(self.request.name, html)
        self.assertIn('Ceftriaxone 1g', html)
        self.assertIn('CEF-2026-009', html)
        self.assertIn('Stability data reviewed and accepted by QA.', html)

    def test_report_lists_every_approval_level(self):
        html = self._render_html(self.request)
        self.assertIn('Approval Levels', html)
        self.assertIn('Report Approver', html)

    def test_report_marks_a_draft_request_as_draft(self):
        html = self._render_html(self.request)
        self.assertIn('DRAFT', html)
        self.assertNotIn('APPROVED', html)

    def test_report_marks_an_approved_request_as_approved(self):
        self.request.action_submit()
        self.request.with_user(self.approver).action_approve()
        html = self._render_html(self.request)
        self.assertIn('APPROVED', html)

    def test_report_can_print_several_requests_at_once(self):
        other = self.request.copy()
        html = self._render_html(self.request | other)
        self.assertIn(self.request.name, html)
        self.assertIn(other.name, html)

    def test_pdf_entry_point_reaches_the_same_template(self):
        # Odoo deliberately falls back to HTML rendering inside a test run, so
        # this covers the PDF entry point without spawning wkhtmltopdf, which
        # needs a live HTTP server to fetch the stylesheets.
        content, _report_type = self.env['ir.actions.report']._render_qweb_pdf(
            REPORT, self.request.ids
        )
        self.assertIn(self.request.name, content.decode())
