from odoo import api, fields, models

# Device states in which its repair is done (the repair service has been delivered).
REPAIRED_STATES = ('qc_testing', 'ready')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    rma_line_id = fields.Many2one('safex.rma.line', string="RMA Device", index=True, copy=False)
    is_service_charge = fields.Boolean(copy=False)
    is_spare_part = fields.Boolean(
        copy=False,
        help="Replaced part shown at 0.00 for transparency. Delivered with the repaired device: the "
             "order's delivery reserves it, and Complete Repair validates it.")
    rma_part_id = fields.Many2one('safex.rma.line.part', string="RMA Spare Part", index=True, copy=False)

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        # A rejected device's parts are taken off the order without a new procurement (its delivery
        # moves are cancelled, see safex.rma.line._remove_from_quotation).
        lines = self if not self.env.context.get('safex_no_stock_rule') else self.filtered(
            lambda line: not line.is_spare_part)
        return super(SaleOrderLine, lines)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)

    @api.depends('rma_line_id.state', 'rma_line_id.part_line_ids.consumed', 'rma_line_id.part_line_ids.quantity')
    def _compute_qty_delivered(self):
        """The service charge is delivered once the device's repair is completed. Replaced parts are
        delivered by the order's delivery (validated on Complete Repair); on older orders without a
        delivery, once consumed by the RMA."""
        super()._compute_qty_delivered()
        for line in self.filtered(lambda sol: sol.rma_line_id and not sol.display_type):
            device = line.rma_line_id
            if line.is_spare_part and not line.move_ids:
                # Orders confirmed before the parts were delivered through the order: parts consumed
                # by the RMA (stock move to the consumption location).
                consumed = device.part_line_ids.filtered(
                    lambda part: part.consumed and part.product_id == line.product_id)
                quantity = sum(part.uom_id._compute_quantity(part.quantity, line.product_uom) for part in consumed)
                line.qty_delivered = min(quantity, line.product_uom_qty)
            elif line.is_service_charge:
                line.qty_delivered = line.product_uom_qty if device.state in REPAIRED_STATES else 0.0
