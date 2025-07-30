from odoo import models, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, grouped=False, final=False):
        invoices = super()._create_invoices(grouped=grouped, final=final)

        for order in self:
            for invoice in order.invoice_ids:
                new_lines = []

                for sol in order.order_line:
                    move_lines = sol.move_ids.filtered(lambda m: m.state == 'done').mapped('move_line_ids')
                    if not move_lines:
                        continue

                    for ml in move_lines:

                        new_line = invoice.env['account.move.line'].new({
                            'move_id': invoice.id,
                            'product_id': sol.product_id.id,
                            'name': sol.name,
                            'quantity': ml.qty_done,
                            'price_unit': sol.price_unit,
                            'account_id': sol.product_id.property_account_income_id.id or sol.order_id.company_id.income_currency_exchange_account_id.id,
                            'imei_no_1': ml.imei_no_1,
                            'imei_no_2': ml.imei_no_2,
                            'battery_sno': ml.battery_sno,
                            'docking_station_sno': ml.docking_station_sno,
                            'lot_id': ml.lot_id.id,
                            'sale_line_ids': [(6, 0, [sol.id])],
                        })
                        new_lines.append((0, 0, new_line._convert_to_write(new_line._cache)))

                if new_lines:

                    invoice.invoice_line_ids.unlink()
                    invoice.write({'invoice_line_ids': new_lines})

        return invoices
