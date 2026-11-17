from odoo import api, models
from odoo.exceptions import UserError


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

    def _safex_lot_for_company(self, company):
        """This device's serial record in ``company`` (the company handling the RMA): the linked serial
        record when there is one, else a new serial record of ``company``'s product with the same
        Internal Reference, linked to this one and carrying its device and warranty data (a device sold
        directly by SafeX UK put on an RMA of SafeX Qatar)."""
        self.ensure_one()
        lot = self.sudo()
        if lot.company_id == company:
            return lot
        Lot = self.env['stock.lot'].sudo()
        existing = lot._safex_device_lots().filtered(lambda other: other.company_id == company)
        if existing:
            return existing.sorted('id')[:1]
        product = lot.product_id
        if product.company_id and product.company_id != company:
            code = product.default_code
            candidates = code and self.env['product.product'].sudo().search([
                ('default_code', '=', code), ('tracking', '=', 'serial'),
                ('company_id', 'in', (company.id, False)),
            ], order='company_id', limit=1)
            if not candidates:
                raise UserError(self.env._(
                    "Device %(serial)s (%(product)s) cannot be put on an RMA of %(company)s: %(company)s has no "
                    "serial-tracked product with the Internal Reference \"%(code)s\".",
                    serial=lot.name, product=product.display_name, company=company.name, code=code or ''))
            product = candidates
        same = Lot.search([('name', '=', lot.name), ('product_id', '=', product.id), ('company_id', '=', company.id)],
                          limit=1)
        if same:
            return same._safex_link_to_source(lot)
        new = Lot.with_company(company).with_context(safex_skip_identifier_check=True).create({
            'name': lot.name,
            'product_id': product.id,
            'company_id': company.id,
            'customer_warranty': lot.customer_warranty,
            'c_start_date': lot.c_start_date,
        })
        new._safex_link_to_source(lot)
        new._safex_sync_warranty_dates()
        new.message_post(body=self.env._(
            "Serial record created for the RMAs handled by %(company)s: same device as %(serial)s (%(seller)s).",
            company=company.name, serial=lot.name, seller=lot.company_id.name))
        return new

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
