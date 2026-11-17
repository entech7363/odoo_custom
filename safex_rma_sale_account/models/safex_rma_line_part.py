from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SafexRmaLinePart(models.Model):
    _inherit = 'safex.rma.line.part'

    sale_line_ids = fields.One2many('sale.order.line', 'rma_part_id', string="Quotation Lines")

    def _safex_delivery_moves(self):
        """Delivery moves of this part on the device's confirmed repair order (the order line created
        for this part; on older orders, the spare part line of the same product)."""
        self.ensure_one()
        lines = self.rma_line_id.sale_line_ids.filtered(
            lambda sl: sl.is_spare_part and sl.order_id.state == 'sale' and sl.product_id == self.product_id)
        line = lines.filtered(lambda sl: sl.rma_part_id == self)[:1] \
            or lines.filtered(lambda sl: not sl.rma_part_id)[:1]
        return line.move_ids.filtered(
            lambda move: move.product_id == self.product_id and move.state != 'cancel'
            and move.location_dest_id.usage == 'customer')

    def _consume(self):
        """Parts on a confirmed repair order are delivered by the order's delivery (validated now, with
        the device's repair completed); the other parts (added after the quotation) are consumed by the
        RMA as before. Blocked when the stock is not available."""
        parts = self.sudo().filtered(lambda p: not p.consumed and p.quantity > 0)
        to_deliver = {}
        for part in parts:
            moves = part._safex_delivery_moves()
            done = moves.filtered(lambda move: move.state == 'done')
            if done and not moves - done:
                part.stock_move_id = done[:1]  # delivery already validated in Inventory
            elif moves:
                to_deliver[part] = (moves - done)[:1]
        delivered = self.browse([part.id for part in to_deliver])
        if to_deliver:
            self._safex_deliver(to_deliver)
        others = parts.filtered(lambda p: not p.consumed) - delivered.sudo()
        return super(SafexRmaLinePart, others.with_env(self.env))._consume()

    def _safex_deliver(self, to_deliver):
        missing = []
        for part, move in to_deliver.items():
            quantity = part.uom_id._compute_quantity(part.quantity, move.product_uom)
            rounding = move.product_uom.rounding
            if float_compare(move.product_uom_qty, quantity, precision_rounding=rounding):
                move.product_uom_qty = quantity  # parts changed after the quotation
            if float_compare(move.quantity, quantity, precision_rounding=rounding) < 0:
                move._action_assign()
            if float_compare(move.quantity, quantity, precision_rounding=rounding) < 0:
                missing.append(self.env._(
                    "%(part)s: needed %(needed)s, available %(available)s in %(location)s",
                    part=part.product_id.display_name, needed=quantity, available=move.quantity,
                    location=move.location_id.display_name))
        if missing:
            device = next(iter(to_deliver)).rma_line_id
            raise UserError(self.env._(
                "Not enough stock to deliver the spare parts of %(device)s:\n%(parts)s\nReceive or move the "
                "parts into stock, then try again.", device=device.display_name, parts="\n".join(missing)))
        moves = self.env['stock.move'].sudo().union(*to_deliver.values())
        moves.picked = True
        moves._action_done()
        for part, move in to_deliver.items():
            part.stock_move_id = move
        for picking in moves.picking_id.filtered(lambda p: p.state == 'done' and not p.date_done):
            picking.date_done = fields.Datetime.now()
