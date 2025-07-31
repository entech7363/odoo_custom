from odoo import models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, grouped=False, final=False):
        invoices = super()._create_invoices(grouped=grouped, final=final)

        for order in self:
            for invoice in order.invoice_ids.filtered(lambda inv: inv.state == 'draft'):
                new_invoice_lines = []

                for line in order.order_line:
                    if not line.product_id.tracking or line.product_id.tracking == 'none':
                        continue

                    move_lines = line.move_ids.filtered(lambda m: m.state == 'done').mapped('move_line_ids')
                    serial_lines = move_lines.filtered(lambda ml: ml.qty_done > 0 and ml.lot_id)

                    for ml in serial_lines:
                        line_vals = line._prepare_invoice_line()
                        line_vals.update({
                            'quantity': 1,
                            'lot_id': ml.lot_id.id,
                            'imei_no_1': ml.imei_no_1,
                            'imei_no_2': ml.imei_no_2,
                            'battery_sno': ml.battery_sno,
                            'docking_station_sno': ml.docking_station_sno,
                        })
                        new_invoice_lines.append((0, 0, line_vals))

                if new_invoice_lines:
                    invoice.write({'invoice_line_ids': [(5, 0, 0)] + new_invoice_lines})
