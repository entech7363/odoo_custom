from odoo import models, fields

class AccountMoveLineSerial(models.Model):
    _name = 'account.move.line.serial'
    _description = 'Invoice Line Serial Info'

    move_line_id = fields.Many2one('account.move.line', required=True, ondelete='cascade')
    imei_no_1 = fields.Char("IMEI 1")
    imei_no_2 = fields.Char("IMEI 2")
    battery_sno = fields.Char("Battery Serial")
    docking_station_sno = fields.Char("Docking Station Serial")
    lot_id = fields.Many2one('stock.production.lot', string="Lot")
