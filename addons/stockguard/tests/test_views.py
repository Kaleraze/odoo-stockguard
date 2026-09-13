from odoo.tests.common import TransactionCase


class TestStockGuardViews(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Ibuprofen 400mg',
            'type': 'product',
            'tracking': 'lot',
        })
        cls.lot = cls.env['stock.lot'].create({
            'name': 'IBU-2026-001',
            'product_id': cls.product.id,
            'company_id': cls.env.company.id,
        })
        groups = [
            cls.env.ref('stockguard.group_warehouse_approver').id,
            cls.env.ref('stock.group_stock_user').id,
        ]
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.requester = Users.create({
            'name': 'View Requester',
            'login': 'sg_view_requester',
            'groups_id': [(6, 0, [cls.env.ref('stockguard.group_warehouse_user').id])],
        })
        cls.approver_1 = Users.create({
            'name': 'View Approver 1',
            'login': 'sg_view_approver_1',
            'groups_id': [(6, 0, groups)],
        })
        cls.approver_2 = Users.create({
            'name': 'View Approver 2',
            'login': 'sg_view_approver_2',
            'groups_id': [(6, 0, groups)],
        })
        cls.request = cls.env['warehouse.approval.request'].create({
            'lot_id': cls.lot.id,
            'quantity': 5.0,
            'reason': 'View test',
            'requested_by_id': cls.requester.id,
            'approval_line_ids': [
                (0, 0, {'level': 1, 'approver_id': cls.approver_1.id}),
                (0, 0, {'level': 2, 'approver_id': cls.approver_2.id}),
            ],
        })

    def test_every_request_view_renders(self):
        for view_type in ('tree', 'form', 'kanban', 'search', 'graph', 'pivot'):
            view = self.env['warehouse.approval.request'].get_view(view_type=view_type)
            self.assertTrue(view['arch'], "%s view is empty" % view_type)

    def test_kanban_keeps_every_stage_visible_even_when_empty(self):
        groups = self.env['warehouse.approval.request'].read_group(
            domain=[('id', '=', self.request.id)],
            fields=['state'],
            groupby=['state'],
        )
        self.assertEqual(
            [group['state'] for group in groups],
            ['draft', 'pending_approval', 'approved', 'rejected'],
        )

    def test_lot_form_carries_the_stockguard_fields(self):
        arch = self.env['stock.lot'].get_view(view_type='form')['arch']
        self.assertIn('quality_state', arch)
        self.assertIn('is_restricted', arch)
        self.assertIn('action_open_approval_requests', arch)

    def test_lot_tree_carries_the_quality_state(self):
        arch = self.env['stock.lot'].get_view(view_type='tree')['arch']
        self.assertIn('quality_state', arch)

    def test_menu_and_action_are_reachable(self):
        action = self.env.ref('stockguard.action_warehouse_approval_request')
        self.assertEqual(action.res_model, 'warehouse.approval.request')
        menu = self.env.ref('stockguard.menu_warehouse_approval_request')
        self.assertEqual(menu.action.id, action.id)

    def test_lot_counts_its_approval_requests(self):
        self.assertEqual(self.lot.approval_request_count, 1)

    def test_lot_smart_button_opens_only_its_own_requests(self):
        action = self.lot.action_open_approval_requests()
        self.assertEqual(action['res_model'], 'warehouse.approval.request')
        self.assertIn(('lot_id', '=', self.lot.id), action['domain'])
        found = self.env['warehouse.approval.request'].search(action['domain'])
        self.assertEqual(found, self.request)

    def test_waiting_for_me_filter_only_matches_the_current_level(self):
        self.request.action_submit()
        Request = self.env['warehouse.approval.request']
        waiting_on_first = Request.search([
            ('pending_approver_ids', 'in', self.approver_1.id),
        ])
        waiting_on_second = Request.search([
            ('pending_approver_ids', 'in', self.approver_2.id),
        ])
        self.assertIn(self.request, waiting_on_first)
        self.assertNotIn(self.request, waiting_on_second)

    def test_waiting_for_me_filter_follows_the_approval_chain(self):
        self.request.action_submit()
        self.request.with_user(self.approver_1).action_approve()
        Request = self.env['warehouse.approval.request']
        waiting_on_second = Request.search([
            ('pending_approver_ids', 'in', self.approver_2.id),
        ])
        self.assertIn(self.request, waiting_on_second)

    def test_draft_requests_are_waiting_on_nobody(self):
        found = self.env['warehouse.approval.request'].search([
            ('pending_approver_ids', 'in', self.approver_1.id),
        ])
        self.assertNotIn(self.request, found)
