from odoo import models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    def _compute_rma_count(self):
        counts = dict(self.env['safex.rma.line']._read_group(
            [('lot_id', 'in', self.ids)], ['lot_id'], ['__count']))
        for lot in self:
            lot.rma_count = counts.get(lot, 0)

    def action_view_rmas(self):
        self.ensure_one()
        rmas = self.env['safex.rma.line'].search([('lot_id', '=', self.id)]).rma_id
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("RMAs"),
            'res_model': 'safex.rma',
            'view_mode': 'list,form',
            'domain': [('id', 'in', rmas.ids)],
        }
