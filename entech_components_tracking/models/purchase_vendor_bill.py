from odoo import models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_create_invoice(self):
        res = super().action_create_invoice()

        for order in self:
            for bill in order.invoice_ids.filtered(lambda b: b.state == 'draft'):
                new_invoice_lines = []

                for line in order.order_line:
                    if not line.product_id.tracking or line.product_id.tracking == 'none':
                        continue

                    move_lines = line.move_ids.filtered(lambda m: m.state == 'done').mapped('move_line_ids')
                    serial_lines = move_lines.filtered(lambda ml: ml.qty_done > 0 and ml.lot_id)

                    for ml in serial_lines:
                        line_vals = line._prepare_account_move_line()
                        account = line.product_id.property_account_expense_id or \
                                  line.product_id.categ_id.property_account_expense_categ_id

                        if not account:
                            raise UserError(f"Missing expense account for product {line.product_id.display_name}")

                        line_vals.update({
                            'quantity': 1,
                            'account_id': account.id,
                            'lot_id': ml.lot_id.id,
                            'imei_no_1': ml.imei_no_1,
                            'imei_no_2': ml.imei_no_2,
                            'battery_sno': ml.battery_sno,
                            'docking_station_sno': ml.docking_station_sno,
                        })
                        new_invoice_lines.append((0, 0, line_vals))

                if new_invoice_lines:
                    bill.write({'invoice_line_ids': [(5, 0, 0)] + new_invoice_lines})

        return res
