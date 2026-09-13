from odoo import _, api, fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    supplier_id = fields.Many2one(
        comodel_name='res.partner',
        string='Supplier',
    )
    received_date = fields.Date(
        string='Received Date',
    )
    quality_state = fields.Selection(
        selection=[
            ('pending', 'Pending Inspection'),
            ('passed', 'Passed'),
            ('failed', 'Failed'),
        ],
        string='Quality State',
        default='pending',
        required=True,
        tracking=True,
    )
    is_restricted = fields.Boolean(
        string='Movement Restricted',
        help="Restricted lots need an approved warehouse request before they can be moved.",
        tracking=True,
    )
    approval_request_ids = fields.One2many(
        comodel_name='warehouse.approval.request',
        inverse_name='lot_id',
        string='Approval Requests',
    )
    approval_request_count = fields.Integer(
        string='Approval Request Count',
        compute='_compute_approval_request_count',
    )

    @api.depends('approval_request_ids')
    def _compute_approval_request_count(self):
        for lot in self:
            lot.approval_request_count = len(lot.approval_request_ids)

    def action_open_approval_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'warehouse.approval.request',
            'view_mode': 'tree,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {'default_lot_id': self.id},
        }
