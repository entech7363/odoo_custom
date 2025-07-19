
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import timedelta


class StockLotComponentLine(models.Model):
    _name = 'stock.lot.component.line'
    _description = 'Stock Lot Component Line'

    lot_id = fields.Many2one('stock.lot', string='Lot')
    product_part_id = fields.Many2one('product.part', string='Product Part')
    serial_number = fields.Char(string='Serial No')
    v_expiry_date = fields.Date(string='Vendor Expiry Date', compute='_compute_expiry_dates', store=True)
    c_expiry_date = fields.Date(string='Customer Expiry Date', compute='_compute_expiry_dates', store=True)

    @api.depends('lot_id.v_start_date', 'lot_id.c_start_date', 'product_part_id')
    def _compute_expiry_dates(self):
        for line in self:
            line.v_expiry_date = False
            line.c_expiry_date = False

            lot = line.lot_id
            v_start = lot.v_start_date
            c_start = lot.c_start_date

            product = lot.product_id
            if not product:
                continue

            tmpl = product.product_tmpl_id
            if not tmpl:
                continue

            component = tmpl.component_ids.filtered(
                lambda c: c.product_part_id == line.product_part_id and c.serial_number
            )

            if component:

                comp = component[0]
                vendor_months = comp.vendor_warranty or 0
                customer_months = comp.customer_warranty or 0

                line.v_expiry_date = v_start + relativedelta(months=vendor_months) if v_start else False
                line.c_expiry_date = c_start + relativedelta(months=customer_months) if c_start else False
