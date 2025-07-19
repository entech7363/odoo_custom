from odoo import models,fields,api

class SaleOrderWizard(models.TransientModel):
    _name = 'sale.order.wizard'
    _description = 'Sale Order Wizard'

    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    history_line_ids = fields.One2many('sale.order.line.history.line', 'wizard_id', string='Order History')
    date_order = fields.Datetime(string='Order Date')
    product_name = fields.Char(string='Product')
    price = fields.Float(string='Price')
    Customer_Purchase = fields.Char(string="PO Number")
    order_name=fields.Char(string='Order Number')

    @api.model
    def default_get(self, fields_list):
        res = super(SaleOrderWizard, self).default_get(fields_list)

        customer_id = self.env.context.get('default_customer_id')
        product_id = self.env.context.get('default_product_id')
        current_order_name = self.env.context.get('default_order_name')

        history_lines = []

        if customer_id and product_id:
            sale_lines = self.env['sale.order.line'].search([
                ('order_id.partner_id', '=', customer_id),
                ('product_id', '=', product_id),
                ('order_id.state', '!=', 'draft'),
                ('order_id.name', '!=', current_order_name),
            ])

            for line in sale_lines:
                history_lines.append((0, 0, {
                    'date_order': line.order_id.date_order,
                    'product_name': line.product_id.name,
                    'price': line.price_unit,
                    'Customer_Purchase': line.order_id.Customer_Purchase,
                    'order_name': line.order_id.name,
                }))
            res['history_line_ids'] = history_lines

        if customer_id:
            res['customer_id'] = customer_id
        if product_id:
            res['product_id'] = product_id

        return res


class SaleOrderLineHistoryLine(models.TransientModel):
    _name = 'sale.order.line.history.line'
    _description = 'Sale Order Line History Line'

    wizard_id = fields.Many2one('sale.order.wizard', string='Wizard', required=True)
    date_order = fields.Datetime(string='Order Date')
    product_name = fields.Char(string='Product')
    price = fields.Float(string='Price')
    Customer_Purchase= fields.Char(string="PO Number")
    order_name = fields.Char(string='Order Number')
