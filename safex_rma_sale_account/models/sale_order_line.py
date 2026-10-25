from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    rma_line_id = fields.Many2one('safex.rma.line', string="RMA Device", index=True, copy=False)
    is_service_charge = fields.Boolean(copy=False)
    is_spare_part = fields.Boolean(
        copy=False,
        help="Replaced part shown at 0.00 for transparency. Stock is consumed from the RMA "
             "spare parts, so these lines never create deliveries.")

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        lines = self.filtered(lambda line: not line.is_spare_part)
        return super(SaleOrderLine, lines)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)
