from odoo.tests.common import TransactionCase


class TestWarehouseApprovalRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'StockGuard Test Product',
            'type': 'product',
            'tracking': 'lot',
        })
        cls.lot = cls.env['stock.lot'].create({
            'name': 'LOT-TEST-0001',
            'product_id': cls.product.id,
            'company_id': cls.env.company.id,
        })

    def _create_request(self, **values):
        vals = {
            'lot_id': self.lot.id,
            'quantity': 10.0,
            'reason': 'Released after re-inspection',
        }
        vals.update(values)
        return self.env['warehouse.approval.request'].create(vals)

    def test_reference_comes_from_sequence(self):
        request = self._create_request()
        self.assertTrue(request.name.startswith('WAR/'))

    def test_each_request_gets_its_own_reference(self):
        first = self._create_request()
        second = self._create_request()
        self.assertNotEqual(first.name, second.name)

    def test_new_request_defaults(self):
        request = self._create_request()
        self.assertEqual(request.state, 'draft')
        self.assertEqual(request.request_type, 'quarantine_release')
        self.assertEqual(request.requested_by_id, self.env.user)
        self.assertEqual(request.company_id, self.env.company)

    def test_product_is_related_from_lot(self):
        request = self._create_request()
        self.assertEqual(request.product_id, self.product)

    def test_lot_links_back_to_its_requests(self):
        request = self._create_request()
        self.assertIn(request, self.lot.approval_request_ids)

    def test_duplicate_resets_reference_and_state(self):
        request = self._create_request(state='approved')
        copy = request.copy()
        self.assertNotEqual(copy.name, request.name)
        self.assertEqual(copy.state, 'draft')

    def test_approval_lines_are_deleted_with_their_request(self):
        request = self._create_request()
        line = self.env['warehouse.approval.line'].create({
            'request_id': request.id,
            'level': 1,
            'approver_id': self.env.user.id,
        })
        self.assertEqual(line.state, 'pending')
        request.unlink()
        self.assertFalse(line.exists())

    def test_lot_cannot_be_deleted_while_requested(self):
        self._create_request()
        with self.assertRaises(Exception):
            self.lot.unlink()


class TestStockLotExtension(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'StockGuard Lot Product',
            'type': 'product',
            'tracking': 'lot',
        })
        cls.lot = cls.env['stock.lot'].create({
            'name': 'LOT-TEST-0002',
            'product_id': cls.product.id,
            'company_id': cls.env.company.id,
        })

    def test_custom_fields_are_added_to_core_lot(self):
        self.assertEqual(self.lot.quality_state, 'pending')
        self.assertFalse(self.lot.is_restricted)

    def test_custom_fields_are_writable(self):
        partner = self.env['res.partner'].create({'name': 'StockGuard Supplier'})
        self.lot.write({
            'quality_state': 'failed',
            'is_restricted': True,
            'supplier_id': partner.id,
        })
        self.assertEqual(self.lot.quality_state, 'failed')
        self.assertTrue(self.lot.is_restricted)
        self.assertEqual(self.lot.supplier_id, partner)
