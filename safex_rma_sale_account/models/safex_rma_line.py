from odoo import fields, models


class SafexRmaLine(models.Model):
    _inherit = 'safex.rma.line'

    currency_id = fields.Many2one(related='company_id.currency_id')
    service_charge_amount = fields.Monetary(
        string="Repair Service Charge", currency_field='currency_id', tracking=True,
        help="Single amount bundling labour and parts for this device.")
    sale_line_ids = fields.One2many('sale.order.line', 'rma_line_id', string="Quotation Lines")

    def action_reject(self, reason):
        res = super().action_reject(reason)
        self._remove_from_quotation()
        return res

    def _remove_from_quotation(self):
        """Drop the device's section from open quotations, or zero it on confirmed orders."""
        for line in self:
            sale_lines = line.sale_line_ids.sudo()
            draft_lines = sale_lines.filtered(lambda sl: sl.order_id.state in ('draft', 'sent', 'to_approve'))
            draft_lines.unlink()
            confirmed = (sale_lines - draft_lines).filtered(
                lambda sl: sl.order_id.state == 'sale' and not sl.display_type)
            # The device goes back as-is: its spare parts are not delivered.
            confirmed.move_ids.filtered(lambda move: move.state not in ('done', 'cancel'))._action_cancel()
            confirmed.filtered(lambda sl: not sl.invoice_lines).with_context(safex_no_stock_rule=True).write(
                {'product_uom_qty': 0.0})
