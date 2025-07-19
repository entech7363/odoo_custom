from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    show_imei_fields_in_delivery = fields.Boolean(compute='_compute_show_imei_fields_in_delivery', store=False)

    @api.depends('move_line_ids')
    def _compute_show_imei_fields_in_delivery(self):
        for picking in self:
            show = any(
                line.imei_no_1 or line.imei_no_2 or line.battery_sno or line.docking_station_sno
                for line in picking.move_line_ids
            )
            picking.show_imei_fields_in_delivery = show
