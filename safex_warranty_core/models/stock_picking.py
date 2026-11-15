from odoo import api, fields, models
from odoo.exceptions import UserError

from .stock_lot import SAFEX_DEVICE_FIELDS


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    safex_seller_company_id = fields.Many2one(
        'res.company', string="SafeX Seller", compute='_compute_safex_seller_company_id',
        help="Inter-company receipt: the SafeX company that sold these devices. The serial numbers "
             "received must be serials it delivered to this company; they are linked to its serials.")

    @api.depends('picking_type_id', 'partner_id', 'company_id')
    def _compute_safex_seller_company_id(self):
        for picking in self:
            picking.safex_seller_company_id = picking._safex_get_seller_company()

    def _action_done(self):
        for picking in self:
            picking._safex_check_intercompany_serials()
            picking._safex_check_vendor_serials()
        res = super()._action_done()
        self._safex_settle_transit_quants()
        self._safex_update_warranty_dates()
        return res

    def _safex_settle_transit_quants(self):
        """Inter-company receipt from the inter-company transit location: the seller's delivery put
        the seller's serial there (+1), this receipt took this company's serial out of it (-1). Both
        are the same device: the seller's serial leaves the transit location instead, so that no
        device seems to stay in transit and no negative serial is left there."""
        Quant = self.env['stock.quant'].sudo()
        for picking in self.filtered(lambda p: p.state == 'done' and p.picking_type_id.code == 'incoming'):
            seller = picking._safex_get_seller_company()
            if not seller:
                continue
            lines = picking.move_line_ids.filtered(
                lambda ml: ml.state == 'done' and ml.lot_id and ml.location_id.usage == 'transit'
                and picking._safex_is_purchase_move(ml.move_id))
            for line in lines:
                location = line.location_id
                source = (line.lot_id._safex_device_lots() - line.lot_id.sudo()).filtered(
                    lambda lot: lot.company_id == seller)[:1]
                if not source:
                    continue
                seller_qty = sum(Quant._gather(source.product_id, location, lot_id=source, strict=True).mapped('quantity'))
                buyer_qty = sum(Quant._gather(line.product_id, location, lot_id=line.lot_id, strict=True).mapped('quantity'))
                quantity = min(seller_qty, -buyer_qty, line.quantity_product_uom)
                if quantity > 0:
                    Quant._update_available_quantity(source.product_id, location, -quantity, lot_id=source)
                    Quant._update_available_quantity(line.product_id, location, quantity, lot_id=line.lot_id)

    # ------------------------------------------------------------------
    # CR-01: inter-company receipts (a SafeX company buying from another SafeX company)
    # ------------------------------------------------------------------

    def _safex_get_seller_company(self):
        """The SafeX company selling to this company when this is an inter-company receipt (receipt of
        a SafeX company whose partner is another SafeX company's partner), else an empty recordset.
        A return (e.g. of this company's delivery to the other SafeX company) is not a purchase."""
        self.ensure_one()
        Company = self.env['res.company'].sudo()
        company = self.company_id.sudo()
        partner = self.partner_id.sudo().commercial_partner_id
        if self.picking_type_id.code != 'incoming' or not partner.is_safex_internal_entity \
                or not company.partner_id.is_safex_internal_entity or self.return_id:
            return Company
        return Company.search([('partner_id', '=', partner.id), ('id', '!=', company.id)], limit=1)

    @staticmethod
    def _safex_is_purchase_move(move):
        """Moves of an inter-company receipt checked against the seller's deliveries: not returns."""
        return move.product_id.tracking == 'serial' and not move.origin_returned_move_id \
            and not getattr(move, 'to_refund', False)

    def _safex_device_last_move(self, lots):
        """Latest validated receipt / delivery of the device(s) of ``lots``, across all their linked serial
        records (all SafeX companies)."""
        return self.env['stock.move.line'].sudo().search([
            ('lot_id', 'in', lots._safex_device_lots().ids), ('state', '=', 'done'),
            ('picking_id.picking_type_id.code', 'in', ('incoming', 'outgoing')),
        ], order='date desc, id desc', limit=1)

    def _safex_device_stock(self, lots):
        """A quant holding the device(s) of ``lots`` in a stock or transit location, any company."""
        return self.env['stock.quant'].sudo().search([
            ('lot_id', 'in', lots._safex_device_lots().ids),
            ('location_id.usage', 'in', ('internal', 'transit')), ('quantity', '>', 0),
        ], limit=1)

    def _safex_check_device_receivable(self, lot):
        """Receipt from an outside vendor (not a return) of a serial this company already knows: the
        physical device must not be elsewhere, i.e. in stock / transit of a company, or last delivered
        to someone else than this vendor by this company (e.g. sold to another SafeX company or to a
        customer). A device this company sent to this vendor (e.g. vendor repair) can come back."""
        self.ensure_one()
        vendor = self.partner_id.commercial_partner_id
        quant = self._safex_device_stock(lot)
        if quant and quant.location_id.usage == 'transit':
            raise UserError(self.env._(
                "Serial %(serial)s is currently in transit (%(location)s). It cannot be received from %(vendor)s.",
                serial=lot.name, location=quant.location_id.display_name, vendor=vendor.display_name))
        if quant:
            raise UserError(self.env._(
                "Serial %(serial)s is currently in stock of %(holder)s (%(location)s). It cannot be received "
                "from %(vendor)s.", serial=lot.name, holder=quant.company_id.name,
                location=quant.location_id.display_name, vendor=vendor.display_name))
        last = self._safex_device_last_move(lot)
        if last.picking_id.picking_type_id.code == 'outgoing' and not (
                last.company_id == self.company_id and last.picking_id.partner_id.commercial_partner_id == vendor):
            raise UserError(self.env._(
                "Serial %(serial)s is currently with %(holder)s (last moved on %(picking)s). It cannot be "
                "received from %(vendor)s.", serial=lot.name,
                holder=last.picking_id.partner_id.commercial_partner_id.display_name or last.company_id.name,
                picking=last.picking_id.name, vendor=vendor.display_name))

    def _safex_is_vendor_receipt(self):
        """Receipt of a SafeX company from an outside (non-SafeX) partner, not a return."""
        self.ensure_one()
        return self.picking_type_id.code == 'incoming' and not self.return_id \
            and self.company_id.sudo().partner_id.is_safex_internal_entity \
            and not self.partner_id.sudo().commercial_partner_id.is_safex_internal_entity

    def _safex_existing_lot(self, product, serial, lot=None):
        """This company's serial record for a serial number entered on a transfer line."""
        self.ensure_one()
        if lot:
            return lot.sudo()
        normalize = self.env['stock.lot']._safex_normalize_identifier
        lots = self.env['stock.lot'].sudo().search([
            ('company_id', '=', self.company_id.id), ('product_id', '=', product.id), ('name', '=ilike', serial.strip())])
        return lots.filtered(lambda other: normalize(other.name) == normalize(serial))[:1]

    def _safex_check_vendor_serials(self):
        """Vendor receipt (CR-01): a known device can only be received if it is not elsewhere."""
        self.ensure_one()
        if not self._safex_is_vendor_receipt():
            return
        lines = self.move_line_ids.filtered(
            lambda ml: (ml.lot_id or ml.lot_name) and ml.quantity
            and ml.move_id.state not in ('done', 'cancel') and self._safex_is_purchase_move(ml.move_id))
        for line in lines:
            lot = self._safex_existing_lot(line.product_id, line.lot_id.name or line.lot_name, line.lot_id)
            if lot:
                self._safex_check_device_receivable(lot)

    def _safex_seller_products(self, seller, product):
        """The seller's product matching ``product`` (this company's product): same Internal Reference."""
        self.ensure_one()
        buyer = self.company_id
        code = product.default_code
        if not (code or '').strip():
            raise UserError(self.env._(
                "Product %(product)s has no Internal Reference: it is needed to find the same product "
                "in %(seller)s.", product=product.display_name, seller=seller.name))
        Product = self.env['product.product'].sudo()
        same_code = Product.search([('default_code', '=', code), ('company_id', 'in', [buyer.id, False])])
        if len(same_code) > 1:
            raise UserError(self.env._(
                "Internal Reference %(code)s is used by several products in %(company)s: %(products)s.\n"
                "Each device model must have its own Internal Reference.",
                code=code, company=buyer.name, products=", ".join(same_code.mapped('display_name'))))
        seller_products = Product.search([('default_code', '=', code), ('company_id', 'in', [seller.id, False])])
        if not seller_products:
            raise UserError(self.env._(
                "There is no product with Internal Reference %(code)s in %(seller)s: the serial numbers of "
                "%(product)s cannot be matched.", code=code, seller=seller.name, product=product.display_name))
        if len(seller_products) > 1:
            raise UserError(self.env._(
                "Internal Reference %(code)s is used by several products in %(company)s: %(products)s.\n"
                "Each device model must have its own Internal Reference.",
                code=code, company=seller.name, products=", ".join(seller_products.mapped('display_name'))))
        return seller_products

    def _safex_seller_delivered_lots(self, seller, seller_products):
        """[(seller serial, (delivery date, move line id))] of the seller's serials (of ``seller_products``)
        whose latest validated delivery by the seller went to this company, oldest delivery first. A
        serial the seller got back since (received again, or in its stock) is not delivered anymore.
        Transfers are ordered by (date, move line id): several can be validated in the same second."""
        self.ensure_one()
        MoveLine = self.env['stock.move.line'].sudo()
        move_lines = MoveLine.search([
            ('company_id', '=', seller.id),
            ('state', '=', 'done'),
            ('product_id', 'in', seller_products.ids),
            ('lot_id', '!=', False),
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
        ], order='date asc, id asc')
        latest = {}
        for move_line in move_lines:
            latest[move_line.lot_id] = move_line
        buyer_partner = self.company_id.partner_id.commercial_partner_id
        latest = {lot: ml for lot, ml in latest.items()
                  if ml.picking_id.partner_id.commercial_partner_id == buyer_partner}
        if not latest:
            return []
        lot_ids = [lot.id for lot in latest]
        in_stock = set(self.env['stock.quant'].sudo().search([
            ('lot_id', 'in', lot_ids), ('company_id', '=', seller.id),
            ('location_id.usage', '=', 'internal'), ('quantity', '>', 0),
        ]).lot_id.ids)
        taken_back = {}
        for move_line in MoveLine.search([
                ('lot_id', 'in', lot_ids), ('company_id', '=', seller.id), ('state', '=', 'done'),
                ('picking_id.picking_type_id.code', '=', 'incoming')]):
            taken_back.setdefault(move_line.lot_id.id, []).append((move_line.date, move_line.id))
        delivered = [
            (lot, (ml.date, ml.id)) for lot, ml in latest.items()
            if lot.id not in in_stock and not any(
                (date, line_id) > (ml.date, ml.id) for date, line_id in taken_back.get(lot.id, []))]
        return sorted(delivered, key=lambda item: item[1])

    def _safex_received_info(self, lots):
        """{lot id: True when in this company's stock, else (date, move line id) of its latest receipt here}."""
        self.ensure_one()
        if not lots:
            return {}
        company = self.company_id
        info = {}
        for move_line in self.env['stock.move.line'].sudo().search([
                ('lot_id', 'in', lots.ids), ('company_id', '=', company.id), ('state', '=', 'done'),
                ('picking_id.picking_type_id.code', '=', 'incoming')]):
            key = (move_line.date, move_line.id)
            info[move_line.lot_id.id] = max(info.get(move_line.lot_id.id, key), key)
        for lot in self.env['stock.quant'].sudo().search([
                ('lot_id', 'in', lots.ids), ('company_id', '=', company.id),
                ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]).lot_id:
            info[lot.id] = True
        return info

    def _safex_delivered_candidates(self, seller, product):
        """[(seller serial, (delivery date, line id), this company's serial or empty, already received)] of the
        serials the seller delivered to this company on the product with the same Internal Reference."""
        self.ensure_one()
        delivered = self._safex_seller_delivered_lots(seller, self._safex_seller_products(seller, product))
        Lot = self.env['stock.lot'].sudo()
        sources = Lot.browse([lot.id for lot, _date in delivered])
        buyer_lots = Lot.search([
            ('company_id', '=', self.company_id.id), ('product_id', '=', product.id),
            '|', ('name', 'in', sources.mapped('name')), ('safex_source_lot_id', 'in', sources.ids),
        ]) if sources else Lot
        by_name = {lot.name: lot for lot in buyer_lots}
        by_source = {lot.safex_source_lot_id.id: lot for lot in buyer_lots if lot.safex_source_lot_id}
        received = self._safex_received_info(buyer_lots)
        candidates = []
        for source, date in delivered:
            buyer_lot = by_name.get(source.name) or by_source.get(source.id) or Lot
            if not buyer_lot and source.safex_source_lot_id.company_id == self.company_id \
                    and source.safex_source_lot_id.product_id == product:
                buyer_lot = source.safex_source_lot_id  # device coming back to the company it came from
                received.update(self._safex_received_info(buyer_lot))
            state = received.get(buyer_lot.id) if buyer_lot else None
            is_received = state is True or bool(state and state >= date)
            # The device must not have moved since the seller's delivery (on any of its serial records).
            if not is_received and self._safex_device_last_move(source).id != date[1]:
                continue
            candidates.append((source, date, buyer_lot, is_received))
        return candidates

    def _safex_check_delivered_serial(self, seller, product, serial, candidates=None):
        """(seller serial or empty, this company's serial or empty) of a serial number entered on this
        inter-company receipt. It must have been delivered by the seller to this company (on the
        product with the same Internal Reference) and must not be received yet. A serial of this
        company coming back from the seller it was delivered to is accepted too (seller serial empty)."""
        self.ensure_one()
        if candidates is None:
            candidates = self._safex_delivered_candidates(seller, product)
        normalize = self.env['stock.lot']._safex_normalize_identifier
        Lot = self.env['stock.lot'].sudo()
        already_received = None
        for source, _date, buyer_lot, received in candidates:
            if normalize(source.name) == normalize(serial):
                if not received:
                    return source, buyer_lot
                already_received = source.name
        # This company's own serial, last delivered to the seller (e.g. sent back without a return).
        own = Lot.search([('company_id', '=', self.company_id.id), ('product_id', '=', product.id),
                          ('name', '=ilike', serial.strip())])
        own = own.filtered(lambda lot: normalize(lot.name) == normalize(serial))[:1]
        if own and self._safex_received_info(own).get(own.id) is True:
            already_received = own.name
        elif own and not self._safex_device_stock(own):
            # The device's latest move (all its serial records) must be this company's delivery to the seller.
            last = self._safex_device_last_move(own)
            if last.company_id == self.company_id and last.picking_id.picking_type_id.code == 'outgoing' \
                    and last.picking_id.partner_id.commercial_partner_id == seller.partner_id:
                return Lot, own
        if already_received:
            raise UserError(self.env._(
                "Serial %(serial)s is already received in %(buyer)s.", serial=already_received, buyer=self.company_id.name))
        raise UserError(self.env._(
            "Serial %(serial)s was not delivered by %(seller)s to %(buyer)s (product %(product)s).",
            serial=serial, seller=seller.name, buyer=self.company_id.name, product=product.display_name))

    def _safex_receive_seller_lot(self, source, product, buyer_lot=None):
        """This company's serial record of the seller's serial ``source``: the existing one (e.g. a
        device coming back) or a new one with the same number, linked to ``source`` and carrying its
        device data (IMEIs, other serial, factory warranty, battery / docking station serials)."""
        self.ensure_one()
        if not source:
            return buyer_lot.with_env(self.env)
        if buyer_lot is None:
            buyer_lot = self.env['stock.lot'].sudo().search([
                ('name', '=', source.name), ('product_id', '=', product.id), ('company_id', '=', self.company_id.id),
            ], limit=1)
        if buyer_lot:
            return buyer_lot._safex_link_to_source(source).with_env(self.env)
        source = source.sudo()
        lot = self.env['stock.lot'].sudo().create({
            'name': source.name,
            'product_id': product.id,
            'company_id': self.company_id.id,
            'safex_source_lot_id': source.id,
            **{name: source[name] for name in SAFEX_DEVICE_FIELDS if source[name]},
        })
        lot._safex_copy_component_serials(source)
        return lot.with_env(self.env)

    def action_safex_load_intercompany_serials(self):
        """Fill this inter-company receipt with the serial numbers the seller SafeX company delivered
        to this company and that are not received yet (same Internal Reference), up to the ordered
        quantities. What is available is loaded (and marked picked: the rest goes to a backorder on
        validation); missing quantities are reported."""
        self.ensure_one()
        seller = self._safex_get_seller_company()
        if not seller:
            raise UserError(self.env._("This is not a receipt from another SafeX company."))
        if self.state in ('done', 'cancel'):
            raise UserError(self.env._("This receipt is already done or cancelled."))
        if self.state == 'draft':
            self.action_confirm()
        moves = self.move_ids.filtered(lambda move: move.state not in ('done', 'cancel')
                                       and self._safex_is_purchase_move(move))
        if not moves:
            raise UserError(self.env._("There is no product tracked by serial number to receive."))
        self._safex_release_invalid_reservations(seller, moves)
        needs = {move: int(move.product_qty) - len(move.move_line_ids.filtered(lambda ml: ml.lot_id or ml.lot_name))
                 for move in moves}
        if all(need <= 0 for need in needs.values()):
            raise UserError(self.env._(
                "This receipt is already complete: every unit to receive has a serial number."))
        normalize = self.env['stock.lot']._safex_normalize_identifier
        on_receipt = {normalize(name) for name in self.move_line_ids.lot_id.mapped('name')
                      + self.move_line_ids.mapped('lot_name') if name}
        loaded = self.env['stock.lot']
        shortages = []
        candidates_by_product = {}
        for move, needed in needs.items():
            if needed <= 0:
                continue
            product = move.product_id
            if product not in candidates_by_product:
                candidates_by_product[product] = self._safex_delivered_candidates(seller, product)
            found = 0
            for source, _date, buyer_lot, received in candidates_by_product[product]:
                if found >= needed:
                    break
                if received or normalize(source.name) in on_receipt:
                    continue
                lot = self._safex_receive_seller_lot(source, product, buyer_lot)
                move._safex_assign_received_lot(lot)
                on_receipt.add(normalize(source.name))
                loaded |= lot
                found += 1
            if found < needed:
                shortages.append(self.env._(
                    "%(product)s: %(found)s of %(needed)s", product=product.display_name, found=found, needed=needed))
        # The moves follow their quantities again (e.g. after releasing stale reservations): Ready when
        # every unit has its serial, partially available otherwise.
        moves._recompute_state()
        if not loaded:
            raise UserError(self.env._(
                "%(seller)s has no delivered serial number waiting to be received by %(buyer)s for these "
                "products. Check that %(seller)s validated its delivery to %(buyer)s.",
                seller=seller.name, buyer=self.company_id.name))
        message = self.env._("%(count)s serial number(s) loaded from %(seller)s.", count=len(loaded), seller=seller.name)
        if shortages:
            message = "%s\n%s" % (message, self.env._(
                "Not enough serial numbers delivered by %(seller)s yet: %(shortages)s. The rest of the "
                "quantity can be received later (backorder).", seller=seller.name, shortages="; ".join(shortages)))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning' if shortages else 'success',
                'message': message,
                'sticky': bool(shortages),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _safex_release_invalid_reservations(self, seller, moves):
        """Lines standard Odoo reserved on this receipt from old quants of the transit location (before
        inter-company receipts were excluded from reservation) whose serial was not delivered by the
        seller: their reservation is released and they are removed, so the seller's serials can be
        loaded. Serials entered by the user (not reserved) are kept and checked on validation."""
        Quant = self.env['stock.quant'].sudo()
        candidates_by_product = {}
        to_release = self.env['stock.move.line']
        for line in moves.move_line_ids.filtered(lambda ml: ml.lot_id and not ml.picked):
            reserved = sum(Quant._gather(line.product_id, line.location_id, lot_id=line.lot_id, strict=True)
                           .mapped('reserved_quantity'))
            if reserved <= 0:
                continue
            product = line.product_id
            if product not in candidates_by_product:
                candidates_by_product[product] = self._safex_delivered_candidates(seller, product)
            try:
                self._safex_check_delivered_serial(seller, product, line.lot_id.name,
                                                   candidates=candidates_by_product[product])
            except UserError:
                to_release |= line
        if to_release:
            to_release.with_context(safex_standard_reservation=True).unlink()

    def _safex_check_intercompany_serials(self):
        """On validation of an inter-company receipt, every serial number (loaded or typed) must be a
        serial delivered by the seller to this company and not received yet; it is then linked to the
        seller's serial (device data copied). Returns are not checked."""
        self.ensure_one()
        seller = self._safex_get_seller_company()
        if not seller:
            return
        lines = self.move_line_ids.filtered(
            lambda ml: (ml.lot_id or ml.lot_name) and ml.quantity
            and ml.move_id.state not in ('done', 'cancel') and self._safex_is_purchase_move(ml.move_id))
        candidates_by_product = {}
        for line in lines:
            product = line.product_id
            if product not in candidates_by_product:
                candidates_by_product[product] = self._safex_delivered_candidates(seller, product)
            source, buyer_lot = self._safex_check_delivered_serial(
                seller, product, line.lot_id.name or line.lot_name, candidates=candidates_by_product[product])
            lot = self._safex_receive_seller_lot(source, product, buyer_lot)
            if line.lot_id != lot:
                line.write({'lot_id': lot.id, 'lot_name': lot.name})

    def _safex_update_warranty_dates(self):
        """Start the warranty clocks from the validated transfers:
        - incoming receipt (GRN) from a vendor starts the factory warranty;
        - first outgoing delivery to a dealer (not a SafeX entity) starts the dealer warranty.
        Receipts and deliveries between SafeX entities (inter-company sales) start nothing.

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
            partner = picking.partner_id.commercial_partner_id
            if company.partner_id.is_safex_internal_entity:
                # The dates belong to the device: all its serial records (linked SafeX companies).
                lots._safex_device_lots()._safex_sync_warranty_dates()
            for lot in lots:
                if code == 'incoming':
                    vals = {}
                    # An inter-company receipt (SafeX company buying from another SafeX company) is not
                    # the GRN: the factory warranty comes from the seller's serial (original vendor receipt).
                    if not lot.v_start_date and not (
                            company.partner_id.is_safex_internal_entity and partner.is_safex_internal_entity):
                        vals['v_start_date'] = date_done
                    if not lot.vendor_warranty:
                        vals['vendor_warranty'] = lot.product_id._safex_factory_warranty_months(company)
                    if vals:
                        lot.write(vals)
                else:
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
SAFEX_IMEI_FIELDS = ('imei_no_1', 'imei_no_2')
SAFEX_FACTORY_WARRANTY_FIELDS = ('v_start_date', 'vendor_warranty')
SAFEX_DEALER_WARRANTY_FIELDS = ('c_start_date', 'customer_warranty')


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _safex_lots_to_protect(self, vals):
        lots = self.lot_id
        if vals.get('lot_id'):
            lots |= self.env['stock.lot'].browse(vals['lot_id'])
        return lots.sudo().filtered(lambda lot: lot._safex_is_safex_lot())

    def _safex_lot_imei_vals(self, lot_id, vals):
        """IMEIs a SafeX serial brings to a new transfer line: the boxes not typed in vals."""
        lot = self.env['stock.lot'].browse(lot_id).sudo() if lot_id else self.env['stock.lot']
        if not lot or not lot._safex_is_safex_lot():
            return {}
        return {name: lot[name] for name in SAFEX_IMEI_FIELDS if lot[name] and not vals.get(name)}

    def _safex_lot_change_imei_vals(self, new_lot):
        """IMEIs to put on this line when its serial becomes new_lot (a SafeX serial):
        - the new serial's IMEI when it has one;
        - otherwise an IMEI carried over from the previous serial is cleared, so it can't be
          copied onto the new serial; a value typed for a serial without IMEI is kept."""
        self.ensure_one()
        old_lot = self.lot_id.sudo()
        res = {}
        for name in SAFEX_IMEI_FIELDS:
            if new_lot[name]:
                if self[name] != new_lot[name]:
                    res[name] = new_lot[name]
            elif self[name] and old_lot and old_lot != new_lot and self[name] == old_lot[name]:
                res[name] = False
        return res

    @api.model_create_multi
    def create(self, vals_list):
        # A SafeX serial reserved or picked on a line brings its IMEIs with it (Entech only does
        # this on deliveries); the IMEIs are typed once, on the first receipt.
        for vals in vals_list:
            vals.update(self._safex_lot_imei_vals(vals.get('lot_id'), vals))
        return super().create(vals_list)

    @api.onchange('lot_name', 'lot_id')
    def _onchange_safex_intercompany_serial(self):
        """Inter-company receipt: warn as soon as a serial number is entered that the seller SafeX
        company did not deliver to this company, or that is already received (blocked on validation)."""
        picking = self.picking_id or self.move_id.picking_id
        serial = self.lot_name or self.lot_id.name
        if not picking or not serial or self.product_id.tracking != 'serial' \
                or (self.move_id and not picking._safex_is_purchase_move(self.move_id)):
            return
        seller = picking._safex_get_seller_company()
        try:
            if seller:
                picking._safex_check_delivered_serial(seller, self.product_id, serial)
            elif picking.company_id and picking._safex_is_vendor_receipt():
                lot = picking._safex_existing_lot(self.product_id, serial, self.lot_id)
                if lot:
                    picking._safex_check_device_receivable(lot)
        except UserError as error:
            return {'warning': {'title': self.env._("Inter-company receipt"), 'message': error.args[0]}}

    @api.onchange('lot_id')
    def _onchange_lot_id_safex_imei(self):
        for line in self:
            lot = line.lot_id.sudo()
            if lot and lot._safex_is_safex_lot():
                for name in SAFEX_IMEI_FIELDS:
                    if lot[name]:
                        line[name] = lot[name]
                    elif line[name] and line._origin.lot_id and line[name] == line._origin.lot_id.sudo()[name]:
                        line[name] = False

    def write(self, vals):
        new_lot = self.env['stock.lot'].browse(vals['lot_id']).sudo() if vals.get('lot_id') else None
        if new_lot and new_lot._safex_is_safex_lot():
            # Serial set or changed on the lines: show that serial's IMEIs (values typed in vals win).
            groups = {}
            for line in self:
                # An empty box sent along (e.g. Entech's "add serial" button) is not a typed value.
                extra = {name: value for name, value in line._safex_lot_change_imei_vals(new_lot).items()
                         if not vals.get(name)}
                key = tuple(sorted(extra.items()))
                groups[key] = groups.get(key, self.browse()) | line
            if any(groups):
                for key, lines in groups.items():
                    lines._safex_write(dict(vals, **dict(key)))
                return True
        return self._safex_write(vals)

    def _safex_write(self, vals):
        lots = self._safex_lots_to_protect(vals)
        before = {lot.id: {name: lot[name] for name in SAFEX_PROTECTED_LOT_FIELDS} for lot in lots}
        identifiers_before = lots._safex_identifier_snapshot()
        # Inter-company transfer (CR-01): the factory warranty comes from the original vendor receipt
        # (copied from the seller's serial), the dealer warranty from the delivery to the dealer: the
        # dates typed on a transfer between SafeX entities must not replace / start them.
        intercompany = self.filtered(lambda ml: ml.move_id.safex_intercompany_transfer)
        restore = (SAFEX_FACTORY_WARRANTY_FIELDS if any(ml.picking_code == 'incoming' for ml in intercompany) else ()) \
            + (SAFEX_DEALER_WARRANTY_FIELDS if any(ml.picking_code == 'outgoing' for ml in intercompany) else ())
        # entech_components_tracking rewrites the serial's IMEIs / component serials on every save:
        # only the numbers that really change are checked for uniqueness, once, below.
        res = super(StockMoveLine, self.with_context(safex_skip_identifier_check=True)).write(vals)
        # entech_components_tracking writes the line's IMEIs and warranty values to the serial even
        # when they are blank: keep the SafeX serial's values (a dealer verifies with serial + IMEI).
        for lot in lots:
            erased = {name: value for name, value in before[lot.id].items() if value and not lot[name]}
            erased.update({name: before[lot.id][name] for name in restore
                           if name in SAFEX_FACTORY_WARRANTY_FIELDS and before[lot.id][name]
                           and lot[name] != before[lot.id][name]})
            erased.update({name: before[lot.id][name] for name in restore
                           if name in SAFEX_DEALER_WARRANTY_FIELDS and lot[name] != before[lot.id][name]})
            if erased:
                lot.with_context(safex_skip_identifier_check=True).write(erased)
        lots._safex_check_identifiers_unique(identifiers_before)
        # On a validated SafeX transfer the validation dates must stay (BRD 3).
        done = self.filtered(lambda ml: ml.state == 'done' and ml.lot_id
                             and ml.company_id.partner_id.is_safex_internal_entity)
        if done:
            done.lot_id._safex_sync_warranty_dates()
        return res
