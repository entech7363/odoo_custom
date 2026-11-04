from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

WARRANTY_CLASSIFICATION = [
    ('under_warranty', "Under Warranty"),
    ('out_of_warranty', "Out of Warranty"),
    ('warranty_rejected', "Warranty Rejected"),
    ('no_fault_found', "No Fault Found"),
    ('physical_damage', "Physical Damage"),
    ('replacement_recommended', "Replacement Recommended"),
]


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
        return super().create(vals_list)

    @api.depends('dealer_warranty_expiry')
    def _compute_dealer_warranty_status(self):
        today = fields.Date.context_today(self)
        for lot in self:
            if not lot.dealer_warranty_expiry:
                lot.dealer_warranty_status = 'not_started'
            else:
                lot.dealer_warranty_status = 'under_warranty' if lot.dealer_warranty_expiry >= today else 'expired'

    @api.constrains('name', 'company_id')
    def _check_safex_serial_unique_across_entities(self):
        """BRD 2/12: a serial is registered once across the SafeX entities (companies whose
        partner is flagged 'SafeX Internal Entity'). Other companies are not affected."""
        lots = self.filtered(lambda lot: lot.name and lot.company_id.partner_id.is_safex_internal_entity)
        for lot in lots:
            others = self.sudo().with_context(active_test=False).search([
                ('name', 'ilike', lot.name.strip()),
                ('company_id', '!=', lot.company_id.id),
                ('company_id.partner_id.is_safex_internal_entity', '=', True),
            ]).filtered(lambda other: other.name.strip().lower() == lot.name.strip().lower())
            if others:
                raise ValidationError(self.env._(
                    "Serial number %(serial)s is already registered in %(company)s. "
                    "A serial number can exist in only one SafeX entity.",
                    serial=lot.name, company=others[0].company_id.name))

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
        """(factory GRN date, dealer delivery date) of this serial, read from its validated transfers
        in any company: the first receipt, and the first delivery to a dealer. Returns, and sales
        between SafeX entities, are ignored. None when there is no such transfer."""
        self.ensure_one()
        move_lines = self.env['stock.move.line'].sudo().search([
            ('lot_id', '=', self.id),
            ('state', '=', 'done'),
            ('picking_id.picking_type_id.code', 'in', ('incoming', 'outgoing')),
            ('move_id.origin_returned_move_id', '=', False),
        ], order='date asc, id asc')

        def day(move_line):
            return fields.Date.context_today(self, move_line.picking_id.date_done or move_line.date)

        receipt = move_lines.filtered(lambda ml: ml.picking_id.picking_type_id.code == 'incoming')[:1]
        delivery = move_lines.filtered(
            lambda ml: ml.picking_id.picking_type_id.code == 'outgoing'
            and ml.picking_id.partner_id
            and not ml.picking_id.partner_id.commercial_partner_id.is_safex_internal_entity)[:1]
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

    def _get_dealer_delivery_move_lines(self, dealer_partner):
        """Done outgoing deliveries of this lot to the dealer, across all companies,
        ignoring inter-company sales between SafeX entities."""
        self.ensure_one()
        commercial = dealer_partner.commercial_partner_id
        move_lines = self.env['stock.move.line'].sudo().search([
            ('lot_id', '=', self.id),
            ('state', '=', 'done'),
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
        ], order='date desc')
        return move_lines.filtered(
            lambda ml: not ml.picking_id.partner_id.commercial_partner_id.is_safex_internal_entity
            and ml.picking_id.partner_id.commercial_partner_id == commercial
        )

    def _is_delivered_to_dealer(self, dealer_partner):
        """True when this serial was delivered (done) to the dealer's company, from any SafeX entity."""
        self.ensure_one()
        return bool(dealer_partner and self._get_dealer_delivery_move_lines(dealer_partner))

    @staticmethod
    def _safex_normalize_identifier(value):
        """Identifiers are compared without spaces and case ('snr 0005' == 'SNR0005')."""
        return ''.join(str(value or '').split()).lower()

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
        """Cross-company verification for the dealer portal (DES00104, BRD 2).

        BRD 2: the dealer enters the product Serial Number + IMEI 1 or IMEI 2, and both must belong
        to the same device. The device must have been delivered to the dealer's company, whichever
        SafeX entity sold it.

        On success returns the product, delivery date and last RMA (dealer-safe data only:
        never warranty, stock, locations or costs).
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
        # 'ilike' narrows the candidates in SQL; the exact comparison (no spaces, any case) decides.
        candidates = self.sudo().with_context(active_test=False).search([('name', 'ilike', str(serial_no).strip())])
        normalize = self._safex_normalize_identifier
        lots = candidates.filtered(lambda lot: normalize(lot.name) == serial and imei in (
            normalize(lot.imei_no_1) or None, normalize(lot.imei_no_2) or None))
        for lot in lots:
            move_lines = lot._get_dealer_delivery_move_lines(dealer)
            if move_lines:
                if not lot.dealer_delivery_date:
                    lot.dealer_delivery_date = fields.Date.to_date(move_lines[-1].date)
                return dict(lot._safex_portal_device_info(), verified=True, lot_id=lot.id)
        return failure
