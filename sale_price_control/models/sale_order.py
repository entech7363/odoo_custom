from odoo import models,fields, api,exceptions
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    approval_step_sequence = fields.Integer(string="Approval Step", default=0)
    state = fields.Selection(
        selection_add=[('draft', 'Quotation'),
        ('to_approve', 'To Approve'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('cancel', 'Cancelled')],
        string="Status")

    show_approve_button = fields.Boolean(compute='_compute_show_approve_button')

    @api.depends('state', 'user_id')
    def _compute_show_approve_button(self):

        for order in self:
            order.show_approve_button = order.state == 'to_approve'

    def _check_approval_step_sequence(self):
        for order in self:
            if order.approval_step_sequence > 1:
                raise UserError("This order has already been approved.")

    def action_approve(self):

        for order in self:
            if order.state == 'to_approve':

                order.approval_step_sequence += 1

                order.with_context(from_approval_wizard=True).action_confirm()
                order.write({'state': 'sale'})

    def action_confirm(self):
        for order in self:
                if self._context.get('from_approval_wizard') and order.state != 'to_approve':
                    order.write({
                        'state': 'to_approve',
                        'user_id': self.env.uid,
                    })


                if self._context.get('from_approval_wizard') and order.state == 'to_approve':
                    order.write({
                        'state': 'to_approve',
                        'user_id': self.env.uid,
                    })



        for order in self:

            for line in order.order_line:

                product_cost = line.product_id.standard_price
                minimum_price = line.product_id.minimum_price
                product_uom = line.product_uom
                uom_qty = line.product_uom_qty
                cost_per_unit = line.product_id.uom_id._compute_price(product_cost, product_uom)



                if line.price_unit  < minimum_price:

                    view = self.env.ref('sale_price_control.sale_order_approval_wizard_form').sudo()
                    return {
                        'name': 'Approval Required',
                        'type': 'ir.actions.act_window',
                        'view_type': 'form',
                        'view_mode': 'form',
                        'res_model': 'sale.order.approval.wizard',
                        'views': [(view.id, 'form')],
                        'view_id': view.id,
                        'target': 'new',
                        'context': {
                            'default_sale_order_id': order.id,
                            'default_message': (
                                f"The unit price {line.price_unit:.2f} for product is below the minimum price {minimum_price:.2f}."
                            ),
                        }
                    }


        return super(SaleOrder, self).action_confirm()

