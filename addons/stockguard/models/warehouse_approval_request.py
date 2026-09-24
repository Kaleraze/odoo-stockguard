from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class WarehouseApprovalRequest(models.Model):
    _name = 'warehouse.approval.request'
    _description = 'Warehouse Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    request_type = fields.Selection(
        selection=[
            ('quarantine_release', 'Quarantine Release'),
            ('quality_override', 'Quality Override'),
            ('quantity_adjustment', 'Quantity Adjustment'),
            ('disposal', 'Disposal'),
        ],
        string='Request Type',
        required=True,
        default='quarantine_release',
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ('0', 'Normal'),
            ('1', 'Urgent'),
        ],
        string='Priority',
        default='0',
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending_approval', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        required=True,
        default='draft',
        copy=False,
        index=True,
        tracking=True,
        group_expand='_group_expand_state',
    )
    lot_id = fields.Many2one(
        comodel_name='stock.lot',
        string='Lot/Serial Number',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        related='lot_id.product_id',
        store=True,
        readonly=True,
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        required=True,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
    )
    requested_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    request_date = fields.Datetime(
        string='Request Date',
        required=True,
        default=fields.Datetime.now,
    )
    approval_line_ids = fields.One2many(
        comodel_name='warehouse.approval.line',
        inverse_name='request_id',
        string='Approval Levels',
        copy=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    current_level = fields.Integer(
        string='Current Level',
        compute='_compute_approval_progress',
        help="The approval level that is waiting for a decision right now.",
    )
    pending_approver_ids = fields.Many2many(
        comodel_name='res.users',
        string='Waiting On',
        compute='_compute_approval_progress',
        search='_search_pending_approver_ids',
    )
    can_approve = fields.Boolean(
        string='Can Approve',
        compute='_compute_can_approve',
        help="Whether the current user is the one this request is waiting on.",
    )

    @api.depends('approval_line_ids.state', 'approval_line_ids.level')
    def _compute_approval_progress(self):
        for request in self:
            pending = request.approval_line_ids.filtered(
                lambda line: line.state == 'pending'
            )
            level = min(pending.mapped('level')) if pending else 0
            request.current_level = level
            request.pending_approver_ids = pending.filtered(
                lambda line: line.level == level
            ).approver_id

    @api.depends('state', 'pending_approver_ids')
    @api.depends_context('uid')
    def _compute_can_approve(self):
        for request in self:
            request.can_approve = (
                request.state == 'pending_approval'
                and self.env.user in request.pending_approver_ids
            )

    @api.model
    def _group_expand_state(self, states, domain, order=None):
        return [key for key, _label in self._fields['state'].selection]

    def _search_pending_approver_ids(self, operator, value):
        if operator not in ('in', '='):
            raise NotImplementedError(_(
                "'Waiting On' can only be searched with '=' or 'in'."
            ))
        user_ids = value if isinstance(value, (list, tuple)) else [value]
        pending_lines = self.env['warehouse.approval.line'].search([
            ('state', '=', 'pending'),
            ('approver_id', 'in', user_ids),
            ('request_id.state', '=', 'pending_approval'),
        ])
        waiting_on_them = pending_lines.filtered(
            lambda line: line.level == line.request_id.current_level
        )
        return [('id', 'in', waiting_on_them.request_id.ids)]

    @api.constrains('quantity')
    def _check_quantity_is_positive(self):
        for request in self:
            if request.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))

    @api.constrains('approval_line_ids', 'requested_by_id')
    def _check_requester_is_not_an_approver(self):
        for request in self:
            if request.requested_by_id in request.approval_line_ids.approver_id:
                raise ValidationError(_(
                    "%(user)s raised this request and cannot approve it as well.",
                    user=request.requested_by_id.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'warehouse.approval.request'
                ) or _('New')
        return super().create(vals_list)

    def unlink(self):
        if any(request.state not in ('draft', 'rejected') for request in self):
            raise UserError(_("Only draft or rejected requests can be deleted."))
        return super().unlink()

    def action_submit(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))
            if not request.approval_line_ids:
                raise UserError(_(
                    "Add at least one approval level before submitting."
                ))
            request.state = 'pending_approval'

    def action_approve(self):
        for request in self:
            line = request._get_decidable_line()
            line.write({
                'state': 'approved',
                'decision_date': fields.Datetime.now(),
            })
            still_pending = request.approval_line_ids.filtered(
                lambda approval: approval.state == 'pending'
            )
            if not still_pending:
                request.state = 'approved'
                request._apply_approval_effect()

    def action_reject(self):
        for request in self:
            line = request._get_decidable_line()
            line.write({
                'state': 'rejected',
                'decision_date': fields.Datetime.now(),
            })
            request.state = 'rejected'

    def action_reset_to_draft(self):
        for request in self:
            if request.state != 'rejected':
                raise UserError(_(
                    "Only rejected requests can be sent back to draft."
                ))
            request.approval_line_ids.write({
                'state': 'pending',
                'decision_date': False,
            })
            request.state = 'draft'

    def _get_decidable_line(self):
        """Return the approval line the current user is allowed to decide now."""
        self.ensure_one()
        if self.state != 'pending_approval':
            raise UserError(_("This request is not waiting for approval."))
        line = self.approval_line_ids.filtered(
            lambda approval: approval.state == 'pending'
            and approval.level == self.current_level
            and approval.approver_id == self.env.user
        )
        if not line:
            raise UserError(_(
                "This request is waiting for level %(level)s, which is not yours "
                "to decide.",
                level=self.current_level,
            ))
        return line[0]

    def _apply_approval_effect(self):
        self.ensure_one()
        if self.request_type == 'quarantine_release':
            self.lot_id.sudo().is_restricted = False
