from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    state = fields.Selection(selection_add=
                             [('to_approve', 'To Approve'),
                              ('sent',)], ondelete={'to_approve': 'cascade'})
    show_approve_button = fields.Boolean(compute='_compute_show_approve_button')
    approval_step_sequence = fields.Integer(string='Approval Step Sequence', default=0)

    @api.depends('state', 'user_id')
    def _compute_show_approve_button(self):
        for order in self:
            steps = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('sequence', '=', order.approval_step_sequence)
            ])
            user_ids = steps.mapped('user_id').ids
            is_admin = self.env.user.has_group('inter_sale_and_purchase_approvals.group_approval')
            order.show_approve_button = order.state == 'to_approve' and (self.env.uid in user_ids or is_admin)

    def _check_approval_step_sequence(self):
        approval_steps = self.env['approval.steps'].search([('type', '=', 'purchase')])
        sequence_numbers = approval_steps.mapped('sequence')
        if len(sequence_numbers) != len(set(sequence_numbers)):
            raise ValidationError("Duplicate sequence numbers exist in purchase approval steps.")

    def button_confirm(self):
        self._check_approval_step_sequence()
        for order in self:
            steps = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('minimum_amount', '<=', order.amount_total)
            ], order='sequence asc')

            if steps:

                first_sequence = min(steps.mapped('sequence'))
                order.write({
                    'state': 'to_approve',
                    'approval_step_sequence': first_sequence
                })
            else:
                super(PurchaseOrder, order).button_confirm()
        return True

    def button_approve_po(self):
        for order in self:
            is_admin = self.env.user.has_group('inter_sale_and_purchase_approvals.group_approval')  # here the admin

            # If admin,then approving the sales
            if is_admin:
                super(PurchaseOrder, order).button_approve()
                return
            next_sequence = order.approval_step_sequence + 1
            next_steps = self.env['approval.steps'].search([
                ('type', '=', 'purchase'),
                ('sequence', '=', next_sequence),
                ('minimum_amount', '<=', order.amount_total)
            ])

            if next_steps:
                order.write({
                    'state': 'to_approve',
                    'approval_step_sequence': next_sequence
                })
            else:
                order.write({'state': 'purchase'})
                super(PurchaseOrder, order).button_approve()

    def button_cancel(self):
        self.write({'state': 'cancel'})
