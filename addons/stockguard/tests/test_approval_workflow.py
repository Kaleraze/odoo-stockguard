from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase
from psycopg2 import IntegrityError
from odoo.tools import mute_logger


class TestApprovalWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Amoxicillin 250mg',
            'type': 'product',
            'tracking': 'lot',
        })
        cls.lot = cls.env['stock.lot'].create({
            'name': 'AMOX-2026-001',
            'product_id': cls.product.id,
            'company_id': cls.env.company.id,
            'is_restricted': True,
        })
        cls.requester = cls._create_user('sg_requester', 'group_warehouse_user')
        cls.approver_1 = cls._create_user('sg_approver_1', 'group_warehouse_approver')
        cls.approver_2 = cls._create_user('sg_approver_2', 'group_warehouse_approver')

    @classmethod
    def _create_user(cls, login, group):
        return cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [
                cls.env.ref('stockguard.%s' % group).id,
                cls.env.ref('stock.group_stock_user').id,
            ])],
        })

    def _create_request(self, levels=(1, 2), **values):
        approvers = {1: self.approver_1, 2: self.approver_2}
        vals = {
            'lot_id': self.lot.id,
            'quantity': 40.0,
            'reason': 'Quarantine released after lab re-test',
            'requested_by_id': self.requester.id,
            'approval_line_ids': [
                (0, 0, {'level': level, 'approver_id': approvers[level].id})
                for level in levels
            ],
        }
        vals.update(values)
        return self.env['warehouse.approval.request'].create(vals)

    # --- progress tracking -------------------------------------------------

    def test_current_level_is_the_lowest_pending_one(self):
        request = self._create_request()
        self.assertEqual(request.current_level, 1)
        self.assertEqual(request.pending_approver_ids, self.approver_1)

    def test_current_level_moves_on_after_a_decision(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.approver_1).action_approve()
        self.assertEqual(request.current_level, 2)
        self.assertEqual(request.pending_approver_ids, self.approver_2)

    def test_can_approve_depends_on_who_is_looking(self):
        request = self._create_request()
        request.action_submit()
        self.assertTrue(request.with_user(self.approver_1).can_approve)
        self.assertFalse(request.with_user(self.approver_2).can_approve)

    # --- submitting --------------------------------------------------------

    def test_submit_moves_request_to_pending_approval(self):
        request = self._create_request()
        request.action_submit()
        self.assertEqual(request.state, 'pending_approval')

    def test_submit_needs_at_least_one_approval_level(self):
        request = self._create_request(levels=())
        with self.assertRaises(UserError):
            request.action_submit()

    def test_cannot_submit_twice(self):
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_submit()

    # --- approving ---------------------------------------------------------

    def test_approving_every_level_approves_the_request(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.approver_1).action_approve()
        self.assertEqual(request.state, 'pending_approval')
        request.with_user(self.approver_2).action_approve()
        self.assertEqual(request.state, 'approved')

    def test_a_later_level_cannot_jump_the_queue(self):
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.with_user(self.approver_2).action_approve()

    def test_an_outsider_cannot_approve(self):
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.with_user(self.requester).action_approve()

    def test_cannot_approve_a_draft_request(self):
        request = self._create_request()
        with self.assertRaises(UserError):
            request.with_user(self.approver_1).action_approve()

    def test_approval_stamps_a_decision_date(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.approver_1).action_approve()
        line = request.approval_line_ids.filtered(lambda l: l.level == 1)
        self.assertEqual(line.state, 'approved')
        self.assertTrue(line.decision_date)

    # --- rejecting ---------------------------------------------------------

    def test_rejection_at_the_first_level_rejects_the_whole_request(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.approver_1).action_reject()
        self.assertEqual(request.state, 'rejected')

    def test_rejected_request_can_go_back_to_draft(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.approver_1).action_reject()
        request.action_reset_to_draft()
        self.assertEqual(request.state, 'draft')
        self.assertEqual(
            set(request.approval_line_ids.mapped('state')), {'pending'}
        )

    def test_only_rejected_requests_can_go_back_to_draft(self):
        request = self._create_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_reset_to_draft()

    # --- effect on the lot -------------------------------------------------

    def test_approved_quarantine_release_unlocks_the_lot(self):
        request = self._create_request(request_type='quarantine_release')
        request.action_submit()
        request.with_user(self.approver_1).action_approve()
        self.assertTrue(self.lot.is_restricted)
        request.with_user(self.approver_2).action_approve()
        self.assertFalse(self.lot.is_restricted)

    def test_other_request_types_leave_the_lot_alone(self):
        request = self._create_request(request_type='disposal')
        request.action_submit()
        request.with_user(self.approver_1).action_approve()
        request.with_user(self.approver_2).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertTrue(self.lot.is_restricted)

    # --- business rules ----------------------------------------------------

    def test_requester_cannot_also_be_an_approver(self):
        with self.assertRaises(ValidationError):
            self._create_request(requested_by_id=self.approver_1.id)

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._create_request(quantity=0)

    def test_approval_level_must_start_at_one(self):
        request = self._create_request()
        with self.assertRaises(ValidationError):
            self.env['warehouse.approval.line'].create({
                'request_id': request.id,
                'level': 0,
                'approver_id': self.approver_1.id,
            })

    @mute_logger('odoo.sql_db')
    def test_the_same_level_cannot_be_used_twice(self):
        request = self._create_request(levels=(1,))
        with self.assertRaises(IntegrityError):
            self.env['warehouse.approval.line'].create({
                'request_id': request.id,
                'level': 1,
                'approver_id': self.approver_2.id,
            })
            self.env.flush_all()

    def test_approved_requests_cannot_be_deleted(self):
        request = self._create_request()
        request.action_submit()
        request.with_user(self.approver_1).action_approve()
        request.with_user(self.approver_2).action_approve()
        with self.assertRaises(UserError):
            request.unlink()

    def test_draft_requests_can_be_deleted(self):
        request = self._create_request()
        request.unlink()
        self.assertFalse(request.exists())
