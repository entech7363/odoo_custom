
from odoo import models, fields,api
from dateutil.relativedelta import relativedelta


class StockProductionLot(models.Model):
    _inherit = 'stock.lot'

    imei_no_1 = fields.Char(string="IMEI NO.1")
    imei_no_2 = fields.Char(string="IMEI NO.2")
    v_start_date = fields.Date(string="Vendor Start Date")
    vendor_warranty = fields.Integer(string='Vendor Warranty')
    vendor_expiry_date = fields.Date(
        string="Vendor Expiry Date", compute="_compute_vendor_expiry_date", store=True
    )
    c_start_date = fields.Date(string="Customer Start Date")
    customer_warranty = fields.Integer(string='Customer Warranty')
    customer_expiry_date = fields.Date(
        string="Customer Expiry Date", compute="_compute_customer_expiry_date", store=True
    )

    lot_component_line_ids = fields.One2many('stock.lot.component.line', 'lot_id', string="Component Lines")


    @api.depends('v_start_date', 'vendor_warranty')
    def _compute_vendor_expiry_date(self):
        for lot in self:
            if lot.v_start_date and lot.vendor_warranty:
                lot.vendor_expiry_date = lot.v_start_date + relativedelta(months=lot.vendor_warranty)
            else:
                lot.vendor_expiry_date = False

    @api.depends('c_start_date', 'customer_warranty')
    def _compute_customer_expiry_date(self):
        for lot in self:
            if lot.c_start_date and lot.customer_warranty:
                lot.customer_expiry_date = lot.c_start_date + relativedelta(months=lot.customer_warranty)
            else:
                lot.customer_expiry_date = False




