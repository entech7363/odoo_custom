import re

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL

WARRANTY_CLASSIFICATION = [
    ('under_warranty', "Under Warranty"),
    ('out_of_warranty', "Out of Warranty"),
    ('warranty_rejected', "Warranty Rejected"),
    ('no_fault_found', "No Fault Found"),
    ('physical_damage', "Physical Damage"),
    ('replacement_recommended', "Replacement Recommended"),
]

# Device data copied from the seller's serial to the buyer's serial on an inter-company receipt.
SAFEX_DEVICE_FIELDS = ('imei_no_1', 'imei_no_2', 'other_serial', 'v_start_date', 'vendor_warranty')
# Device numbers kept identical on all the serial records of a device (linked SafeX companies).
SAFEX_SHARED_IDENTIFIER_FIELDS = ('imei_no_1', 'imei_no_2')
# Fields whose change may bring a new identifier on a serial (uniqueness across the SafeX companies).
SAFEX_IDENTIFIER_WRITE_FIELDS = {'name', 'imei_no_1', 'imei_no_2', 'imei_1', 'imei_2', 'company_id', 'product_id'}
# Characters ignored when comparing identifiers: every whitespace (incl. no-break / zero-width spaces).
# The same pattern is used in Python and in PostgreSQL so that both compare the same way.
SAFEX_IGNORED_CHARS = '[\\s\u00a0\u1680\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\ufeff]+'
SAFEX_IGNORED_CHARS_RE = re.compile(SAFEX_IGNORED_CHARS)


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # IMEIs and both warranty clocks are already kept by entech_components_tracking
    # (filled from receipts and deliveries); the SafeX names are aliases of those fields.
    imei_1 = fields.Char(string="IMEI 1", related='imei_no_1', readonly=False)
    imei_2 = fields.Char(string="IMEI 2", related='imei_no_2', readonly=False)
    other_serial = fields.Char(
        string="Other Serial", index='trigram',
        help="Any other identifier printed on the device (e.g. factory or module serial). "
             "Dealers can verify the device with it on the portal.")

    # Factory (purchase-side) warranty: GRN date + 18 months = Entech vendor warranty
    factory_grn_date = fields.Date(
        string="Factory GRN Date", related='v_start_date', readonly=False, groups='base.group_user')
    factory_warranty_months = fields.Integer(
        string="Factory Warranty Months", related='vendor_warranty', readonly=False, groups='base.group_user')
    factory_warranty_expiry = fields.Date(
        string="Factory Warranty Expiry", related='vendor_expiry_date', groups='base.group_user')

    # SafeX dealer (sales-side) warranty: dealer delivery date + 16 months = Entech customer warranty
    dealer_delivery_date = fields.Date(
        string="Dealer Delivery Date", related='c_start_date', readonly=False, groups='base.group_user')
    dealer_warranty_months = fields.Integer(
        string="Dealer Warranty Months", related='customer_warranty', readonly=False, groups='base.group_user')
    dealer_warranty_expiry = fields.Date(
        string="Dealer Warranty Expiry", related='customer_expiry_date', groups='base.group_user')

    # Result of the latest RMA only: the classification itself is kept per RMA device line.
    # The device's own warranty standing is dealer_warranty_status, calculated from the expiry date.
    warranty_classification = fields.Selection(
        WARRANTY_CLASSIFICATION, string="Last RMA Classification", tracking=True, groups='base.group_user',
        help="Classification confirmed at the technical inspection of the latest RMA. "
             "It does not change the device's warranty period.")
    dealer_warranty_status = fields.Selection(
        [('not_started', "Not Started"), ('under_warranty', "Under Warranty"), ('expired', "Expired")],
        string="Dealer Warranty Status", compute='_compute_dealer_warranty_status', groups='base.group_user')

    # Service traceability, written back on repair completion
    last_repair_date = fields.Date(readonly=True, copy=False)
    last_rma_number = fields.Char(string="Last RMA Number", readonly=True, copy=False)
    rma_count = fields.Integer(compute='_compute_rma_count')

    # CR-01: every SafeX company keeps its own serial records. A serial received from another SafeX
    # company (inter-company sale) points to the seller's serial: together they are one physical device.
    safex_source_lot_id = fields.Many2one(
        'stock.lot', string="Source Device", readonly=True, copy=False, index=True, ondelete='restrict',
        help="Serial number of the SafeX company this device was received from (inter-company sale).")
    safex_linked_lot_ids = fields.Many2many(
        'stock.lot', string="Linked Devices", compute='_compute_safex_linked_lot_ids',
        help="Serial records of the same physical device in the other SafeX companies.")
    safex_linked_devices = fields.Char(
        string="Same Device In", compute='_compute_safex_linked_lot_ids',
        help="Serial records of the same physical device in the other SafeX companies.")
    safex_source_device = fields.Char(
        string="Source Device", compute='_compute_safex_linked_lot_ids',
        help="Serial number of the SafeX company this device was received from (inter-company sale).")

    @api.model_create_multi
    def create(self, vals_list):
        # Warranty periods: product override, else the company default (BRD: 16 / 18 months).
        for vals in vals_list:
            product = self.env['product.product'].browse(vals.get('product_id')).sudo()
            company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
            if not vals.get('customer_warranty') and not vals.get('dealer_warranty_months'):
                vals['customer_warranty'] = product._safex_dealer_warranty_months(company)
            if not vals.get('vendor_warranty') and not vals.get('factory_warranty_months'):
                vals['vendor_warranty'] = product._safex_factory_warranty_months(company)
        lots = super().create(vals_list)
        if not self.env.context.get('safex_skip_identifier_check'):
            lots._safex_check_identifiers_unique()
        return lots

    @api.depends('dealer_warranty_expiry')
    def _compute_dealer_warranty_status(self):
        today = fields.Date.context_today(self)
        for lot in self:
            if not lot.dealer_warranty_expiry:
                lot.dealer_warranty_status = 'not_started'
            else:
                lot.dealer_warranty_status = 'under_warranty' if lot.dealer_warranty_expiry >= today else 'expired'

    def write(self, vals):
        if 'name' in vals:
            for lot in self:
                if vals['name'] != lot.name and len(lot._safex_device_lots()) > 1:
                    raise UserError(self.env._(
                        "The serial number %(serial)s cannot be changed: it is linked to the same device "
                        "in another SafeX company (%(linked)s).",
                        serial=lot.name, linked=lot.safex_linked_devices))
        # Uniqueness (CR-01): only the identifiers this write really changes are checked, so that
        # legacy duplicates don't block stock operations rewriting the same values (Entech rewrites
        # the IMEIs on every transfer line save).
        check = not self.env.context.get('safex_skip_identifier_check') and SAFEX_IDENTIFIER_WRITE_FIELDS & set(vals)
        before = self._safex_identifier_snapshot() if check else None
        shared = [name for name in SAFEX_SHARED_IDENTIFIER_FIELDS if name in vals] \
            + [alias for alias in ('imei_1', 'imei_2') if alias in vals]
        old_shared = {lot.id: {name: lot.sudo()[name] for name in SAFEX_SHARED_IDENTIFIER_FIELDS} for lot in self} \
            if shared else {}
        res = super().write(vals)
        if check:
            if {'company_id', 'product_id'} & set(vals):
                before = None  # moved to another company / product: every number is checked
            self._safex_check_identifiers_unique(before)
        if shared and not self.env.context.get('safex_propagating'):
            self._safex_propagate_identifiers(old_shared)
        return res

    def _safex_propagate_identifiers(self, old_values):
        """Keep the IMEIs of the linked serial records (same device) up to date."""
        for lot in self.sudo():
            changed = {name: lot[name] for name in SAFEX_SHARED_IDENTIFIER_FIELDS
                       if lot[name] and self._safex_normalize_identifier(lot[name])
                       != self._safex_normalize_identifier(old_values.get(lot.id, {}).get(name))}
            if not changed:
                continue
            others = lot._safex_device_lots() - lot
            if others:
                # Same device: no conflict between them; the new values were checked on this serial.
                others.with_context(safex_propagating=True, safex_skip_identifier_check=True).write(changed)

    def _safex_propagate_component_serials(self):
        """Keep the battery / docking station serials of the linked serial records up to date."""
        if self.env.context.get('safex_propagating'):
            return
        for lot in self.sudo():
            others = lot._safex_device_lots() - lot
            for other in others.with_context(safex_propagating=True, safex_skip_identifier_check=True):
                other._safex_copy_component_serials(lot)

    def _safex_is_safex_lot(self):
        """True for a serial of a SafeX entity: owned by a company whose partner is flagged
        'SafeX Internal Entity'."""
        self.ensure_one()
        return bool(self.sudo().company_id.partner_id.is_safex_internal_entity)

    def _safex_device_lots(self):
        """All serial records of the same physical device(s), self included (sudo): the source chain
        followed in both directions (seller's serial <- buyer's serial <- ...)."""
        Lot = self.env['stock.lot'].sudo().with_context(active_test=False)
        result = self.sudo()
        frontier = result.filtered(lambda lot: isinstance(lot.id, int))
        while frontier:
            found = frontier.safex_source_lot_id | Lot.search([('safex_source_lot_id', 'in', frontier.ids)])
            frontier = found - result
            result |= frontier
        return result

    @api.depends('safex_source_lot_id')
    def _compute_safex_linked_lot_ids(self):
        for lot in self:
            linked = lot._safex_device_lots() - lot.sudo()
            lot.safex_linked_lot_ids = linked
            lot.safex_linked_devices = ", ".join(
                f"{other.name} ({other.company_id.name})" for other in linked) or False
            source = lot.sudo().safex_source_lot_id
            lot.safex_source_device = f"{source.name} ({source.company_id.name})" if source else False

    @api.constrains('safex_source_lot_id', 'company_id')
    def _check_safex_source_lot(self):
        if self._has_cycle('safex_source_lot_id'):
            raise ValidationError(self.env._("A serial number cannot be its own source device."))
        for lot in self.filtered('safex_source_lot_id'):
            if lot.sudo().safex_source_lot_id.company_id == lot.company_id:
                raise ValidationError(self.env._(
                    "Serial number %s: the source device must belong to another SafeX company.", lot.name))

    @api.model
    def _safex_component_part_ids(self, kind=None):
        """Product parts flagged as battery (kind='battery') or docking station (kind='dock');
        {'battery': ids, 'dock': ids} without kind."""
        if kind is None:
            return {kind: self._safex_component_part_ids(kind) for kind in ('battery', 'dock')}
        flag = 'is_battery' if kind == 'battery' else 'is_docking_station'
        return self.env['product.component'].sudo().search([(flag, '=', True)]).product_part_id.ids

    def _safex_component_serials(self, part_ids=None):
        """{'battery': serial, 'dock': serial} of this device, from its component lines
        (entech_components_tracking). False when unknown."""
        self.ensure_one()
        part_ids = part_ids or self._safex_component_part_ids()
        lines = self.sudo().lot_component_line_ids
        return {kind: lines.filtered(lambda line: line.serial_number and line.product_part_id.id in ids)[:1]
                .serial_number or False for kind, ids in part_ids.items()}

    def _safex_identifiers(self, part_ids=None):
        """[(group, label, raw value, normalized value)] of the numbers that identify this device:
        serial number, IMEI 1 / IMEI 2 (one group: an IMEI can't be reused in either box), and every
        battery serial and docking station serial of its component lines."""
        self.ensure_one()
        lot = self.sudo()
        part_ids = part_ids or self._safex_component_part_ids()
        values = [
            ('serial', self.env._("Serial number"), lot.name),
            ('imei', self.env._("IMEI 1"), lot.imei_no_1),
            ('imei', self.env._("IMEI 2"), lot.imei_no_2),
        ]
        labels = {'battery': self.env._("Battery serial"), 'dock': self.env._("Docking station serial")}
        for line in lot.lot_component_line_ids:
            for kind, ids in part_ids.items():
                if line.product_part_id.id in ids:
                    values.append((kind, labels[kind], line.serial_number))
        return [(group, label, value, self._safex_normalize_identifier(value))
                for group, label, value in values if self._safex_normalize_identifier(value)]

    def _safex_identifier_snapshot(self, part_ids=None):
        """{lot id: {(group, normalized value)}} of the SafeX serials (to check only new values)."""
        part_ids = part_ids or self._safex_component_part_ids()
        return {lot.id: {(group, norm) for group, _label, _value, norm in lot._safex_identifiers(part_ids)}
                for lot in self if lot._safex_is_safex_lot()}

    @api.model
    def _safex_serial_lot_sql(self):
        """FROM clause (alias lot) of the serials of serial-tracked products of the SafeX companies."""
        return SQL("""
            stock_lot lot
            JOIN res_company company ON company.id = lot.company_id
            JOIN res_partner partner ON partner.id = company.partner_id AND partner.is_safex_internal_entity
            JOIN product_product product ON product.id = lot.product_id
            JOIN product_template template ON template.id = product.product_tmpl_id AND template.tracking = 'serial'
        """)

    @api.model
    def _safex_normalized_sql(self, column):
        """SQL of an identifier compared like _safex_normalize_identifier (no whitespace, lower case)."""
        return SQL("lower(regexp_replace(%s, %s, '', 'g'))", column, SAFEX_IGNORED_CHARS)

    def _safex_find_identifier_owners(self, group_values, part_ids=None):
        """{(group, normalized value): {lot ids}} of the serials of the SafeX companies using these
        numbers. group_values: {group: set(normalized values)}."""
        part_ids = part_ids or self._safex_component_part_ids()
        self.env['stock.lot'].flush_model(['name', 'imei_no_1', 'imei_no_2', 'company_id'])
        self.env['stock.lot.component.line'].flush_model(['lot_id', 'serial_number', 'product_part_id'])
        safex_lot = self._safex_serial_lot_sql()
        normalized = self._safex_normalized_sql

        queries = []
        if group_values.get('serial'):
            queries.append(SQL("SELECT lot.id, 'serial', %s FROM %s WHERE %s = ANY(%s)",
                               normalized(SQL('lot.name')), safex_lot, normalized(SQL('lot.name')),
                               list(group_values['serial'])))
        if group_values.get('imei'):
            for column in ('imei_no_1', 'imei_no_2'):
                expr = normalized(SQL.identifier('lot', column))
                queries.append(SQL("SELECT lot.id, 'imei', %s FROM %s WHERE %s = ANY(%s)",
                                   expr, safex_lot, expr, list(group_values['imei'])))
        for group in ('battery', 'dock'):
            if group_values.get(group) and part_ids[group]:
                expr = normalized(SQL('component.serial_number'))
                queries.append(SQL("""
                    SELECT lot.id, %s, %s FROM %s
                      JOIN stock_lot_component_line component ON component.lot_id = lot.id
                     WHERE component.product_part_id = ANY(%s) AND %s = ANY(%s)
                """, group, expr, safex_lot, part_ids[group], expr, list(group_values[group])))
        owners = {}
        if queries:
            self.env.cr.execute(SQL(" UNION ALL ").join(queries))
            for lot_id, group, value in self.env.cr.fetchall():
                owners.setdefault((group, value), set()).add(lot_id)
        return owners

    def _safex_check_identifiers_unique(self, before=None):
        """CR-01 (BRD 2/12): the serial number, IMEI 1 / IMEI 2, battery serials and docking station
        serials of a device are registered once across the SafeX companies (companies whose partner
        is flagged 'SafeX Internal Entity'), ignoring whitespace and case. The serial records of the
        same physical device in the other SafeX companies (linked by inter-company receipts) are not
        duplicates. Only serial-tracked products are checked; other companies (e.g. Entech) are not
        affected. ``before`` ({lot id: {(group, normalized value)}}): values already there before the
        change, not checked again (legacy duplicates don't block stock operations)."""
        lots = self.sudo().filtered(
            lambda lot: isinstance(lot.id, int) and lot.product_id.tracking == 'serial' and lot._safex_is_safex_lot())
        if not lots:
            return
        part_ids = self._safex_component_part_ids()
        before = before or {}
        identifiers = {
            lot: [item for item in lot._safex_identifiers(part_ids)
                  if (item[0], item[3]) not in before.get(lot.id, set())]
            for lot in lots}
        group_values = {}
        for values in identifiers.values():
            for group, _label, _value, norm in values:
                group_values.setdefault(group, set()).add(norm)
        if not group_values:
            return
        owners = self._safex_find_identifier_owners(group_values, part_ids)
        for lot in lots:
            if not identifiers[lot]:
                continue
            device_ids = set(lot._safex_device_lots().ids)
            for group, label, value, norm in identifiers[lot]:
                other_ids = owners.get((group, norm), set()) - device_ids
                if not other_ids:
                    continue
                other = self.sudo().browse(min(other_ids))
                if group == 'serial':
                    message = self.env._(
                        "Serial number %(value)s is already registered on %(product)s in %(company)s.",
                        value=value, product=other.product_id.display_name, company=other.company_id.name)
                else:
                    message = self.env._(
                        "%(label)s %(value)s of serial number %(serial)s is already registered on serial "
                        "number %(other)s (%(product)s) in %(company)s.",
                        label=label, value=value, serial=lot.name, other=other.name,
                        product=other.product_id.display_name, company=other.company_id.name)
                raise ValidationError("%s\n%s" % (message, self.env._(
                    "Serial numbers, IMEIs, battery and docking station serials must be unique across the "
                    "SafeX companies.")))

    def _safex_link_to_source(self, source):
        """Make this serial (buyer company) the same device as ``source`` (the seller company's
        serial): set the source when the two are not linked yet, and copy the device data known
        by the seller (IMEIs, other serial, factory warranty, battery / docking station serials)."""
        self.ensure_one()
        lot = self.sudo()
        source = source.sudo()
        vals = {name: source[name] for name in SAFEX_DEVICE_FIELDS if source[name] and lot[name] != source[name]}
        if source not in lot._safex_device_lots():
            vals['safex_source_lot_id'] = source.id
        if vals:
            lot.write(vals)
        lot._safex_copy_component_serials(source)
        return self

    def _safex_copy_component_serials(self, source):
        """Battery / docking station serials of ``source`` written on this serial (on the part of
        this serial's product, or the source's part when the product has no such component)."""
        self.ensure_one()
        lot = self.sudo()
        source_serials = source._safex_component_serials()
        components = lot.product_id.product_tmpl_id.component_ids
        for kind, flag in (('battery', 'is_battery'), ('dock', 'is_docking_station')):
            serial = source_serials[kind]
            if not serial:
                continue
            part = components.filtered(flag)[:1].product_part_id or source.sudo().lot_component_line_ids.filtered(
                lambda line: line.serial_number == serial)[:1].product_part_id
            current = lot.lot_component_line_ids.filtered(lambda line: line.product_part_id == part)
            if current.serial_number == serial and len(current) == 1:
                continue
            current.unlink()
            lot.lot_component_line_ids.create({'lot_id': lot.id, 'product_part_id': part.id, 'serial_number': serial})

    def action_apply_safex_dealer_warranty(self):
        """Recalculate the SafeX warranties of the selected serials and log every change:
        - dealer delivery date and factory GRN date from the validated transfers (BRD 3);
        - dealer warranty months reset to the SafeX value (product override, else company default);
        - missing factory warranty months filled with the SafeX value."""
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(self.env._("Only Inventory Administrators can recalculate warranties."))
        changed = self.sudo()._safex_sync_warranty_dates()
        for lot in self.sudo():
            months = lot.product_id._safex_dealer_warranty_months(lot.company_id or self.env.company)
            if months and lot.customer_warranty != months:
                old = lot.customer_warranty
                lot.customer_warranty = months
                lot.message_post(body=self.env._(
                    "Dealer warranty reset from %(old)s to %(new)s months (SafeX warranty policy).",
                    old=old or 0, new=months))
                changed |= lot
            if not lot.vendor_warranty:
                factory_months = lot.product_id._safex_factory_warranty_months(lot.company_id or self.env.company)
                if factory_months:
                    lot.vendor_warranty = factory_months
                    lot.message_post(body=self.env._(
                        "Factory warranty set to %s months (SafeX warranty policy).", factory_months))
                    changed |= lot
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._("%(changed)s of %(total)s serial number(s) updated.",
                                      changed=len(changed), total=len(self)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _safex_transfer_dates(self):
        """(factory GRN date, dealer delivery date) of this device, read from the validated transfers
        of all its serial records (linked SafeX companies): the first receipt from a vendor, and the
        first delivery to a dealer. Returns, and receipts / sales between SafeX entities, are
        ignored. None when there is no such transfer."""
        self.ensure_one()
        move_lines = self.env['stock.move.line'].sudo().search([
            ('lot_id', 'in', self._safex_device_lots().ids),
            ('state', '=', 'done'),
            ('picking_id.picking_type_id.code', 'in', ('incoming', 'outgoing')),
            ('move_id.origin_returned_move_id', '=', False),
        ], order='date asc, id asc')

        def day(move_line):
            return fields.Date.context_today(self, move_line.picking_id.date_done or move_line.date)

        def intercompany(move_line):
            return move_line.picking_id.partner_id.commercial_partner_id.is_safex_internal_entity

        receipt = move_lines.filtered(
            lambda ml: ml.picking_id.picking_type_id.code == 'incoming' and not intercompany(ml))[:1]
        delivery = move_lines.filtered(
            lambda ml: ml.picking_id.picking_type_id.code == 'outgoing'
            and ml.picking_id.partner_id and not intercompany(ml))[:1]
        return (day(receipt) if receipt else None), (day(delivery) if delivery else None)

    def _safex_sync_warranty_dates(self):
        """BRD 3: the dealer warranty starts on the actual delivery to the dealer, the factory warranty
        on the GRN date. Dates typed on the transfers are replaced by the validation dates; a serial
        with no such transfer keeps its date. Corrections are logged on the serial.
        Returns the serials that changed."""
        changed = self.browse()
        for lot in self.sudo():
            grn_date, delivery_date = lot._safex_transfer_dates()
            vals = {}
            if grn_date and lot.v_start_date != grn_date:
                vals['v_start_date'] = grn_date
            if delivery_date and lot.c_start_date != delivery_date:
                vals['c_start_date'] = delivery_date
            if not vals:
                continue
            notes = []
            if lot.v_start_date and 'v_start_date' in vals:
                notes.append(self.env._("Factory GRN date %(old)s → %(new)s", old=lot.v_start_date, new=grn_date))
            if lot.c_start_date and 'c_start_date' in vals:
                notes.append(self.env._("Dealer delivery date %(old)s → %(new)s",
                                        old=lot.c_start_date, new=delivery_date))
            lot.write(vals)
            if notes:
                lot.message_post(body=self.env._(
                    "Warranty start corrected from the validated transfers: %s", "; ".join(notes)))
            changed |= lot
        return changed

    def _compute_rma_count(self):
        # Overridden in safex_rma_core once the RMA models exist.
        self.rma_count = 0

    def action_view_rmas(self):
        # Overridden in safex_rma_core.
        return False

    def _is_under_dealer_warranty(self, on_date=None):
        self.ensure_one()
        on_date = on_date or fields.Date.context_today(self)
        lot = self.sudo()
        return bool(lot.dealer_warranty_expiry and lot.dealer_warranty_expiry >= on_date)

    def _safex_outside_delivery_move_lines(self):
        """Done deliveries of this device (all its linked serial records) to partners outside the
        SafeX entities, newest first. Inter-company sales and returns to vendors are ignored."""
        move_lines = self.env['stock.move.line'].sudo().search([
            ('lot_id', 'in', self._safex_device_lots().ids),
            ('state', '=', 'done'),
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
            ('move_id.origin_returned_move_id', '=', False),
        ], order='date desc, id desc')

        def returned(move_line):
            # The customer gave this device back (validated return of this delivery): no longer a sale.
            return any(line.lot_id == move_line.lot_id and line.state == 'done'
                       for line in move_line.move_id.returned_move_ids.move_line_ids)

        return move_lines.filtered(
            lambda ml: ml.picking_id.partner_id
            and not ml.picking_id.partner_id.commercial_partner_id.is_safex_internal_entity
            and not returned(ml))

    def _safex_final_sale_lot(self):
        """The serial record of this device that made the latest sale outside SafeX (product details,
        RMA company). The serial itself when the device was never sold outside SafeX."""
        self.ensure_one()
        return self._safex_outside_delivery_move_lines()[:1].lot_id or self

    def _safex_channel_distributor(self):
        """CR-04: the dealer (commercial partner) of the device's latest sale outside SafeX, across all
        its linked serial records; empty when the device was never sold outside SafeX."""
        self.ensure_one()
        return self._safex_outside_delivery_move_lines()[:1].picking_id.partner_id.commercial_partner_id

    def _get_dealer_delivery_move_lines(self, dealer_partner):
        """Done outgoing deliveries of this device to the dealer, from any SafeX entity (all the
        linked serial records), ignoring inter-company sales between SafeX entities. Newest first."""
        self.ensure_one()
        commercial = dealer_partner.commercial_partner_id
        return self._safex_outside_delivery_move_lines().filtered(
            lambda ml: ml.picking_id.partner_id.commercial_partner_id == commercial)

    def _is_delivered_to_dealer(self, dealer_partner):
        """True when this serial was delivered (done) to the dealer's company, from any SafeX entity."""
        self.ensure_one()
        return bool(dealer_partner and self._get_dealer_delivery_move_lines(dealer_partner))

    @staticmethod
    def _safex_normalize_identifier(value):
        """Identifiers are compared without spaces and case ('snr 0005' == 'SNR0005')."""
        return SAFEX_IGNORED_CHARS_RE.sub('', str(value or '')).lower()

    def _safex_portal_device_info(self):
        """What a dealer sees about a device they have proved they own.

        Warranty data (status, expiry, months), stock, locations and costs are never shown to dealers.
        """
        self.ensure_one()
        lot = self.sudo()
        return {
            'serial_no': lot.name,
            'product_name': lot.product_id.display_name,
            'delivery_date': fields.Date.to_string(lot.dealer_delivery_date) if lot.dealer_delivery_date else '',
            'last_rma': lot.last_rma_number or '',
        }

    @api.model
    def verify_device_for_portal(self, serial_no, imei, dealer_partner_id):
        """Cross-company verification for the dealer portal (DES00104, BRD 2), over the serials of
        all the SafeX companies.

        BRD 2: the dealer enters the product Serial Number + IMEI 1 or IMEI 2, and both must belong
        to the same device. CR-04: the device belongs to the dealer of its LATEST sale outside SafeX
        (commercial partner, whichever SafeX entity sold it):
        - sold to this dealer: status 'own', with the product, delivery date and last RMA;
        - sold to another dealer: status 'other_dealer', with the product and that dealer's name only
          (the dealer may still raise an RMA after confirming);
        - never sold outside SafeX: not found.
        Dealer-safe data only: never warranty, stock, locations, prices or costs.
        """
        failure = {
            'verified': False,
            'message': self.env._(
                "Device verification failed. This device was not found in your delivered purchases."),
        }
        serial = self._safex_normalize_identifier(serial_no)
        imei = self._safex_normalize_identifier(imei)
        if not serial or not imei:
            return failure
        dealer = self.env['res.partner'].sudo().browse(dealer_partner_id).exists()
        if not dealer:
            return failure
        # Serials of the SafeX companies (serial-tracked products) with this number, compared without
        # whitespace and case; the IMEI must be one of the same serial record's IMEIs.
        self.env['stock.lot'].flush_model(['name', 'imei_no_1', 'imei_no_2', 'company_id', 'product_id'])
        self.env.cr.execute(SQL("SELECT lot.id FROM %s WHERE %s = %s ORDER BY lot.id",
                                self._safex_serial_lot_sql(), self._safex_normalized_sql(SQL('lot.name')), serial))
        candidates = self.sudo().browse([row[0] for row in self.env.cr.fetchall()])
        normalize = self._safex_normalize_identifier
        lots = candidates.filtered(lambda lot: imei in (normalize(lot.imei_no_1) or None, normalize(lot.imei_no_2) or None))
        checked = self.browse()
        for lot in lots:
            if lot in checked:
                continue
            checked |= lot._safex_device_lots()
            latest_sale = lot._safex_outside_delivery_move_lines()[:1]
            if not latest_sale:
                continue  # still with SafeX (or only sold between SafeX entities)
            # Linked device (inter-company sale): the serial record of the latest sale to an outside
            # partner gives the product details and the company handling the RMA.
            final = latest_sale.lot_id
            distributor = latest_sale.picking_id.partner_id.commercial_partner_id
            if distributor != dealer.commercial_partner_id:
                return {
                    'verified': True,
                    'status': 'other_dealer',
                    'lot_id': final.id,
                    'serial_no': final.name,
                    'product_name': final.product_id.display_name,
                    'distributor': distributor.name,
                }
            move_lines = lot._get_dealer_delivery_move_lines(dealer)
            if not final.dealer_delivery_date and move_lines:
                final.dealer_delivery_date = fields.Date.to_date(move_lines[-1].date)
            return dict(final._safex_portal_device_info(), verified=True, status='own', lot_id=final.id)
        return failure


class StockLotComponentLine(models.Model):
    _inherit = 'stock.lot.component.line'

    # Battery / docking station serials are unique across the SafeX companies (CR-01), and kept the
    # same on all the serial records of a device. Only new values are checked (see stock.lot.write).

    @api.model_create_multi
    def create(self, vals_list):
        lots = self.env['stock.lot'].browse({vals.get('lot_id') for vals in vals_list if vals.get('lot_id')})
        before = lots._safex_identifier_snapshot()
        lines = super().create(vals_list)
        if not self.env.context.get('safex_skip_identifier_check'):
            lines.lot_id._safex_check_identifiers_unique(before)
        lines.lot_id._safex_propagate_component_serials()
        return lines

    def write(self, vals):
        if not {'serial_number', 'product_part_id', 'lot_id'} & set(vals):
            return super().write(vals)
        lots = self.lot_id
        if vals.get('lot_id'):
            lots |= self.env['stock.lot'].browse(vals['lot_id'])
        before = lots._safex_identifier_snapshot()
        res = super().write(vals)
        if not self.env.context.get('safex_skip_identifier_check'):
            lots._safex_check_identifiers_unique(before)
        lots._safex_propagate_component_serials()
        return res
