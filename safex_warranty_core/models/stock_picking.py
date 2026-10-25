from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        self._safex_update_warranty_dates()
        return res

    def _safex_update_warranty_dates(self):
        """Start the warranty clocks from the validated transfers:
        - incoming receipt (GRN) starts the factory warranty;
        - first outgoing delivery to a dealer (not a SafeX entity) starts the dealer warranty.

        entech_components_tracking copies the start date and months typed on the move to the
        serial; only what is still empty afterwards is filled here (date done, default months).
        """
        for picking in self.filtered(lambda p: p.state == 'done'):
            date_done = fields.Date.to_date(picking.date_done) or fields.Date.context_today(picking)
            company = picking.company_id
            code = picking.picking_type_id.code
            for lot in picking.move_line_ids.lot_id.sudo():
                if code == 'incoming':
                    vals = {}
                    if not lot.v_start_date:
                        vals['v_start_date'] = date_done
                    if not lot.vendor_warranty:
                        vals['vendor_warranty'] = lot.product_id._safex_factory_warranty_months(company)
                    if vals:
                        lot.write(vals)
                elif code == 'outgoing':
                    partner = picking.partner_id.commercial_partner_id
                    if not partner or partner.is_safex_internal_entity:
                        continue
                    vals = {}
                    if not lot.c_start_date:
                        vals['c_start_date'] = date_done
                    if not lot.customer_warranty:
                        vals['customer_warranty'] = lot.product_id._safex_dealer_warranty_months(company)
                    if vals:
                        lot.write(vals)
