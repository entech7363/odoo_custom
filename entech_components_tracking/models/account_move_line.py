from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # imei_no_1 = fields.Char("IMEI No 1")
    # imei_no_2 = fields.Char("IMEI No 2")
    # battery_sno = fields.Char("Battery SNO")
    # docking_station_sno = fields.Char("Docking Station SNO")
    # lot_id = fields.Many2one("stock.lot", string="Lot/Serial")
    #
    # @api.model
    # def create(self, vals):
    #     record = super().create(vals)
    #     record._set_vendor_serial_data()
    #     return record
    #
    # def _set_vendor_serial_data(self):
    #     for line in self:
    #         _logger.info(">>> Checking line: %s", line.name)
    #
    #         if line.move_id.move_type != 'in_invoice':
    #             _logger.info(">>> Not a vendor bill")
    #             continue
    #
    #         if not line.product_id:
    #             _logger.info(">>> No product")
    #             continue
    #
    #         move_lines = False
    #
    #         if line.purchase_line_id:
    #             move_lines = line.purchase_line_id.move_ids.filtered(lambda m: m.state == 'done').mapped(
    #                 'move_line_ids')
    #
    #         if not move_lines:
    #             _logger.info(">>> Trying fallback using move_id name (%s)", line.move_id.name)
    #             move_lines = self.env['stock.move.line'].search([
    #                 ('reference', '=', line.move_id.name),
    #                 ('product_id', '=', line.product_id.id),
    #                 ('state', '=', 'done'),
    #             ], limit=1)
    #
    #         if not move_lines:
    #             _logger.info(">>> No matching move lines found")
    #             continue
    #
    #         ml = move_lines[0]
    #         line.lot_id = ml.lot_id
    #         line.imei_no_1 = ml.imei_no_1
    #         line.imei_no_2 = ml.imei_no_2
    #         line.battery_sno = ml.battery_sno
    #         line.docking_station_sno = ml.docking_station_sno
    #         _logger.info(">>> Serial data copied from move line: %s", ml.id)
