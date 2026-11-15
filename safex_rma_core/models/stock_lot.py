from odoo import api, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    def _safex_device_rmas(self):
        """{lot: RMAs of its whole device (all linked serial records)} that the user can open (record
        rules of the selected companies): the RMAs smart button counts and opens the same records."""
        devices = {lot: lot._safex_device_lots() for lot in self}
        lot_ids = {lot_id for device in devices.values() for lot_id in device.ids}
        rmas_by_lot = {}
        for line in self.env['safex.rma.line'].search([('lot_id', 'in', list(lot_ids))]):
            rmas_by_lot.setdefault(line.lot_id.id, self.env['safex.rma'])
            rmas_by_lot[line.lot_id.id] |= line.rma_id
        result = {}
        for lot, device in devices.items():
            rmas = self.env['safex.rma']
            for lot_id in device.ids:
                rmas |= rmas_by_lot.get(lot_id, rmas)
            result[lot] = rmas
        return result

    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_rma_count(self):
        # CR-01: the RMAs of the whole device, whichever SafeX company's serial record they were raised on.
        for lot, rmas in self._safex_device_rmas().items():
            lot.rma_count = len(rmas)

    @api.model
    def _safex_accessory_serial_exists(self, kind, serial):
        """True if a battery (kind='battery') or docking station (kind='dock') serial number is known in
        any SafeX company: as a component of a device serial (entech_components_tracking), or as the
        serial of a product stocked as that accessory. Not limited to the returned device's own components.
        The match is exact and case-sensitive (only surrounding spaces are ignored)."""
        serial = (serial or '').strip()
        if kind not in ('battery', 'dock') or not serial:
            return False
        safex_companies = self.env['res.company'].sudo().search([('partner_id.is_safex_internal_entity', '=', True)])
        company_ids = [False, *safex_companies.ids]
        component_flag = 'is_battery' if kind == 'battery' else 'is_docking_station'
        parts = self.env['product.component'].sudo().search([(component_flag, '=', True)]).product_part_id
        if parts and self.env['stock.lot.component.line'].sudo().search_count([
            ('serial_number', '=', serial),
            ('product_part_id', 'in', parts.ids),
            ('lot_id.company_id', 'in', company_ids),
        ], limit=1):
            return True
        return bool(self.sudo().search_count([
            ('name', '=', serial),
            ('product_id.product_tmpl_id.safex_accessory_type', '=', kind),
            ('company_id', 'in', company_ids),
        ], limit=1))

    def action_view_rmas(self):
        self.ensure_one()
        rmas = self._safex_device_rmas()[self]
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("RMAs"),
            'res_model': 'safex.rma',
            'view_mode': 'list,form',
            'domain': [('id', 'in', rmas.ids)],
        }
