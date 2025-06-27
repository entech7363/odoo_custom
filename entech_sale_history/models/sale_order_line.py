from odoo import models,fields,api

class saleorderline(models.Model):

    _inherit = 'sale.order.line'






    def action_view_product_history(self):
        view = self.env.ref('entech_sale_history.sale_order_wizard_form').sudo()
        print(view, '..............view')
        return{
            'name':'History of products',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model':'sale.order.wizard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': {
            'default_customer_id': self.order_id.partner_id.id,
            'default_product_id': self.product_id.id,
            'default_order_date': self.order_id.date_order,
            'default_message': f"Please adjust the price or send it for approval."
            }

        }

