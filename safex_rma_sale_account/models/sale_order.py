from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rma_id = fields.Many2one('safex.rma', string="RMA", index=True, copy=False, readonly=True)

    def action_confirm(self):
        """RMA quotations list the replaced parts at 0.00 by design (DES00112), which is always below
        the sale_price_control minimum price. When only those part lines are below it, confirm the
        order through sale_price_control's own "approved" path instead of opening its approval wizard.
        Any other line below its minimum price still goes through the normal approval."""
        rma_orders = self.filtered(lambda so: so.rma_id and not so._safex_needs_price_approval())
        res = True
        if self - rma_orders:
            res = super(SaleOrder, self - rma_orders).action_confirm()
        # sale_price_control returns after the first order of that path: confirm them one by one.
        for order in rma_orders.filtered(lambda so: so.state in ('draft', 'sent', 'to_approve')):
            order.state = 'to_approve'
            super(SaleOrder, order.with_context(from_approval_wizard=True)).action_confirm()
        # The spare parts are reserved as soon as the quotation is approved: missing stock shows before
        # the repair starts (the delivery is validated by Complete Repair).
        self.filtered(lambda so: so.rma_id and so.state == 'sale').picking_ids.filtered(
            lambda picking: picking.state in ('confirmed', 'waiting')).action_assign()
        return res

    def _safex_needs_price_approval(self):
        self.ensure_one()
        return any(
            not line.display_type and not line.is_spare_part
            and line.price_unit < line.product_id.minimum_price
            for line in self.order_line
        )

    def _safex_filter_to_invoice(self):
        """Confirmed orders with something to invoice. An order whose total is 0.00 (warranty /
        manufacturing-defect repairs quoted at no charge, CR-08) is never invoiced."""
        return self.filtered(
            lambda so: so.state == 'sale' and so.invoice_status == 'to invoice'
            and not so.currency_id.is_zero(so.amount_total))
