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

        SafeX entities (BRD 3): the start dates are always the validation dates of the first
        receipt / first dealer delivery, whatever was typed on the transfer. Other companies
        (Entech) keep the dates typed on the transfer; only empty ones are filled here.
        """
        for picking in self.filtered(lambda p: p.state == 'done'):
            date_done = fields.Date.context_today(picking, picking.date_done) if picking.date_done \
                else fields.Date.context_today(picking)
            company = picking.company_id
            code = picking.picking_type_id.code
            if code not in ('incoming', 'outgoing'):
                continue
            lots = picking.move_line_ids.lot_id.sudo()
            if company.partner_id.is_safex_internal_entity:
                lots._safex_sync_warranty_dates()
            for lot in lots:
                if code == 'incoming':
                    vals = {}
                    if not lot.v_start_date:
                        vals['v_start_date'] = date_done
                    if not lot.vendor_warranty:
                        vals['vendor_warranty'] = lot.product_id._safex_factory_warranty_months(company)
                    if vals:
                        lot.write(vals)
                else:
                    partner = picking.partner_id.commercial_partner_id
                    if not partner or partner.is_safex_internal_entity:
                        continue
                    vals = {}
                    if not lot.c_start_date:
                        vals['c_start_date'] = date_done
                    policy_months = lot.product_id._safex_dealer_warranty_months(company)
                    if not lot.customer_warranty or (
                            company.safex_enforce_dealer_warranty and lot.customer_warranty != policy_months):
                        vals['customer_warranty'] = policy_months
                    if vals:
                        lot.write(vals)


# Serial fields that entech_components_tracking copies from every saved transfer line,
# blank values included. On SafeX serials a blank line must not erase them.
SAFEX_PROTECTED_LOT_FIELDS = (
    'imei_no_1', 'imei_no_2', 'v_start_date', 'vendor_warranty', 'c_start_date', 'customer_warranty')


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _safex_lots_to_protect(self, vals):
        lots = self.lot_id
        if vals.get('lot_id'):
            lots |= self.env['stock.lot'].browse(vals['lot_id'])
        return lots.sudo().filtered(lambda lot: lot.company_id.partner_id.is_safex_internal_entity)

    def write(self, vals):
        lots = self._safex_lots_to_protect(vals)
        before = {lot.id: {name: lot[name] for name in SAFEX_PROTECTED_LOT_FIELDS} for lot in lots}
        res = super().write(vals)
        # entech_components_tracking writes the line's IMEIs and warranty values to the serial even
        # when they are blank: keep the SafeX serial's values (a dealer verifies with serial + IMEI).
        for lot in lots:
            erased = {name: value for name, value in before[lot.id].items() if value and not lot[name]}
            if erased:
                lot.write(erased)
        # On a validated SafeX transfer the validation dates must stay (BRD 3).
        done = self.filtered(lambda ml: ml.state == 'done' and ml.lot_id
                             and ml.company_id.partner_id.is_safex_internal_entity)
        if done:
            done.lot_id._safex_sync_warranty_dates()
        return res
