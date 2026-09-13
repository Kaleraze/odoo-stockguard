from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WarehouseApprovalLine(models.Model):
    _name = 'warehouse.approval.line'
    _description = 'Warehouse Approval Level'
    _order = 'request_id, level, id'

    _sql_constraints = [
        (
            'unique_level_per_request',
            'UNIQUE(request_id, level)',
            'Each approval level can only be used once per request.',
        ),
    ]

    request_id = fields.Many2one(
        comodel_name='warehouse.approval.request',
        string='Approval Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    level = fields.Integer(
        string='Level',
        required=True,
        default=1,
        help="Approval order. Level 1 is decided first, then level 2, and so on.",
    )
    approver_id = fields.Many2one(
        comodel_name='res.users',
        string='Approver',
        required=True,
    )
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        required=True,
        default='pending',
    )
    decision_date = fields.Datetime(
        string='Decision Date',
        readonly=True,
    )
    comment = fields.Text(
        string='Comment',
    )
    company_id = fields.Many2one(
        related='request_id.company_id',
        store=True,
        index=True,
    )

    @api.constrains('level')
    def _check_level_is_positive(self):
        for line in self:
            if line.level < 1:
                raise ValidationError(_("Approval level must be 1 or higher."))
