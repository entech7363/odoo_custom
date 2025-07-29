# your_module/models/sale_order_line.py
from odoo import models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    lead_time = fields.Integer(string='Lead Time(Days)')
