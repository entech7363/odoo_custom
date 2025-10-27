from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(selection_add=
                             [('to_approve', 'To Approve'),
                              ('sent',)], ondelete={'to_approve': 'cascade'})
    show_approve_button = fields.Boolean(compute='_compute_show_approve_button')
    approval_step_sequence = fields.Integer(string='Approval Step Sequence', default=0)

    @api.depends('state', 'approval_step_sequence')
    def _compute_show_approve_button(self):
        for order in self:
            steps = self.env['approval.steps'].search([
                ('type', '=', 'sale'),
                ('sequence', '=', order.approval_step_sequence)
            ])
            user_ids = steps.mapped('user_id').ids
            is_admin = self.env.user.has_group('inter_sale_and_purchase_approvals.group_approval')#change to admin

            order.show_approve_button = order.state == 'to_approve' and (self.env.uid in user_ids or is_admin)

    def _check_approval_step_sequence(self):
        approval_steps = self.env['approval.steps'].search([('type', '=', 'sale')])
        sequence_numbers = approval_steps.mapped('sequence')
        if len(sequence_numbers) != len(set(sequence_numbers)):
            raise ValidationError("Duplicate sequence numbers exist in sale approval steps.")

    # def action_confirm(self):
    #     print("jjjjjjjjjjjj")
    #     self._check_approval_step_sequence()
    #     return super(SaleOrder, self).action_confirm()
    #
    def action_confirm(self):
       print("lklkkkkkkkkkkkkkkkkkkkk")
       #self._check_approval_step_sequence()
       for order in self:
            approval_steps = self.env['approval.steps'].search([
                ('type', '=', 'sale'),
                ('minimum_amount', '<=', order.amount_total),
            ], order='sequence asc')

            if approval_steps:
                next_step = approval_steps.filtered(lambda step: step.sequence == order.approval_step_sequence + 1)
                if next_step:
                    order.write({
                        'state': 'to_approve',
                     'user_id': next_step.user_id.id,
                         'approval_step_sequence': next_step.sequence
                    })
                else:
                    super(SaleOrder, order).action_confirm()
            else:
                super(SaleOrder, order).action_confirm()
       return True



    def button_approve(self):
        print("hkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk")
        for order in self:
            is_admin = self.env.user.has_group('inter_sale_and_purchase_approvals.group_approval') #here the admin


            if is_admin:

                super(SaleOrder, order).action_confirm()
                return
            next_sequence = order.approval_step_sequence + 1
            next_steps = self.env['approval.steps'].search([
                ('type', '=', 'sale'),
                ('sequence', '=', next_sequence),
                ('minimum_amount', '<=', order.amount_total),
            ],)
            print("666666666666666666666666666666")
            if next_steps:
                order.write({
                    'state': 'to_approve',
                    'approval_step_sequence': next_sequence
                })
                print("999999999999999999999")
            else:
                super(SaleOrder, order).action_confirm()

    def action_cancel(self):
        self.write({'state': 'cancel'})
