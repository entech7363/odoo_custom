from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    safex_intercompany_transfer = fields.Boolean(
        string="SafeX Inter-company Transfer", compute='_compute_safex_intercompany_transfer',
        help="Transfer between two SafeX entities (e.g. SafeX Qatar -> SafeX UK). The warranty "
             "fields are optional: the shared serial keeps its factory / dealer warranty.")

    @api.depends('picking_id.company_id', 'picking_id.partner_id', 'company_id', 'partner_id')
    def _compute_safex_intercompany_transfer(self):
        for move in self:
            company = (move.picking_id.company_id or move.company_id).sudo()
            partner = (move.picking_id.partner_id or move.partner_id).sudo().commercial_partner_id
            move.safex_intercompany_transfer = bool(
                company.partner_id.is_safex_internal_entity and partner.is_safex_internal_entity)
