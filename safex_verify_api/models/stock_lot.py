from odoo import api, models
from odoo.tools import SQL


class StockLot(models.Model):
    _inherit = 'stock.lot'

    @api.model
    def _safex_public_verify(self, serial_no, imei):
        """CR-02: public verification of a device by Serial Number + IMEI 1 or IMEI 2 (both on the same
        serial record), over the serials of all the SafeX companies, as in the dealer portal.

        Returns {'product': ..., 'distributor': ...} for a device sold outside SafeX (its latest sale:
        product of that serial record, commercial partner it was delivered to), else False (unknown
        device, or still with SafeX / only sold between SafeX entities). Nothing else is ever returned:
        no warranty, stock, locations, prices, customers or internal ids.
        """
        normalize = self._safex_normalize_identifier
        serial, imei = normalize(serial_no), normalize(imei)
        if not serial or not imei:
            return False
        self.env['stock.lot'].flush_model(['name', 'imei_no_1', 'imei_no_2', 'company_id', 'product_id'])
        self.env.cr.execute(SQL("SELECT lot.id FROM %s WHERE %s = %s ORDER BY lot.id",
                                self._safex_serial_lot_sql(), self._safex_normalized_sql(SQL('lot.name')), serial))
        candidates = self.sudo().browse([row[0] for row in self.env.cr.fetchall()])
        lots = candidates.filtered(
            lambda lot: imei in (normalize(lot.imei_no_1) or None, normalize(lot.imei_no_2) or None))
        checked = self.browse()
        for lot in lots:
            if lot in checked:
                continue
            checked |= lot._safex_device_lots()
            latest_sale = lot._safex_outside_delivery_move_lines()[:1]
            if latest_sale:
                return {
                    'product': latest_sale.lot_id.product_id.display_name,
                    'distributor': latest_sale.picking_id.partner_id.commercial_partner_id.name,
                }
        return False
