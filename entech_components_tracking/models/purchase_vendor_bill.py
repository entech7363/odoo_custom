from odoo import models, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_create_invoice(self):
        res = super().action_create_invoice()

        for order in self:
            for bill in order.invoice_ids:
                new_lines = []

                for pol in order.order_line:
                    move_lines = pol.move_ids.filtered(lambda m: m.state == 'done').mapped('move_line_ids')
                    if not move_lines:
                        continue

                    for ml in move_lines:
                        new_line = bill.env['account.move.line'].new({
                            'move_id': bill.id,
                            'product_id': pol.product_id.id,
                            'name': pol.name,
                            'quantity': 1,
                            'price_unit': pol.price_unit,
                            'account_id': pol.product_id.property_account_expense_id.id or pol.order_id.company_id.expense_currency_exchange_account_id.id,
                            'product_uom_id': pol.product_uom.id,
                            'imei_no_1': ml.imei_no_1,
                            'imei_no_2': ml.imei_no_2,
                            'battery_sno': ml.battery_sno,
                            'docking_station_sno': ml.docking_station_sno,
                            'lot_id': ml.lot_id.id,
                        })
                        new_lines.append((0, 0, new_line._convert_to_write(new_line._cache)))

                if new_lines:
                    bill.invoice_line_ids.unlink()
                    bill.write({'invoice_line_ids': new_lines})

        return res
