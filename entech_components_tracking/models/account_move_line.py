from odoo import models, fields

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    imei_no_1 = fields.Char("IMEI No 1")
    imei_no_2 = fields.Char("IMEI No 2")
    battery_sno = fields.Char("Battery SNO")
    docking_station_sno = fields.Char("Docking Station SNO")
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial")

