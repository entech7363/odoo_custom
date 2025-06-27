
from odoo import models, fields,api

class StockProductionLot(models.Model):
    _inherit = 'stock.lot'

    imei_no_1 = fields.Char(string="IMEI NO.1")
    imei_no_2 = fields.Char(string="IMEI NO.2")
    v_start_date = fields.Date(string="Vendor Start Date")
    vendor_warranty = fields.Integer(string='Vendor Warranty')
    c_start_date = fields.Date(string="Customer Start Date")
    customer_warranty = fields.Integer(string='Customer Warranty')
    lot_component_line_ids = fields.One2many('stock.lot.component.line', 'lot_id', string="Component Lines")




