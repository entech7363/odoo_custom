from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    v_start_date = fields.Date(string="Vendor Start Date")
    vendor_warranty = fields.Integer(string='Vendor Warranty')
    c_start_date = fields.Date(string="Customer Start Date")
    customer_warranty = fields.Integer(string='Customer Warranty')

    show_vendor_warranty = fields.Boolean(compute='_compute_show_warranty_flags', store=False)
    show_customer_warranty = fields.Boolean(compute='_compute_show_warranty_flags', store=False)

    @api.depends('picking_type_id.code')
    def _compute_show_warranty_flags(self):
        for move in self:
            move_type = move.picking_type_id.code
            move.show_vendor_warranty = move_type == 'incoming'
            move.show_customer_warranty = move_type == 'outgoing'
            print(f"Move Type :{move.picking_type_id.code}")

