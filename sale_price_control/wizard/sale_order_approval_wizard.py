from odoo import models, fields, api, exceptions


class SaleOrderApprovalWizard(models.TransientModel):
    _name = 'sale.order.approval.wizard'
    _description = 'Sale Order Approval Wizard'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", required=True)
    message = fields.Text(string="Message", readonly=True)

    def action_send_for_approval(self):
        self.sale_order_id.with_context(from_approval_wizard=True).action_confirm()

