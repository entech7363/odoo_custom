from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'


    show_delivery_serials = fields.Boolean(string="Print Serial Numbers",)

    show_imei_columns = fields.Boolean(string="Show IMEI Columns", compute="_compute_show_imei_columns", store=False)

    sale_order_date = fields.Datetime(string="Sale Order Date", compute="_compute_sale_order_date", store=False)

    @api.depends('invoice_line_ids.imei_no_1', 'invoice_line_ids.imei_no_2',
                 'invoice_line_ids.battery_sno', 'invoice_line_ids.docking_station_sno')
    def _compute_show_imei_columns(self):
        for move in self:
            move.show_imei_columns = any(
                line.imei_no_1 or line.imei_no_2 or line.battery_sno or line.docking_station_sno
                for line in move.invoice_line_ids
            )

    @api.depends('invoice_origin')
    def _compute_sale_order_date(self):
        for record in self:
            sale_order = self.env['sale.order'].search([('name', '=', record.invoice_origin)], limit=1)
            record.sale_order_date = sale_order.date_order if sale_order else False