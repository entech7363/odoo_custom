from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    safex_intercompany_transfer = fields.Boolean(
        string="SafeX Inter-company Transfer", compute='_compute_safex_intercompany_transfer',
        help="Transfer between two SafeX entities (e.g. SafeX Qatar -> SafeX UK). The warranty "
             "fields are optional: the serial keeps the factory warranty of the seller's serial.")

    @api.depends('picking_id.company_id', 'picking_id.partner_id', 'company_id', 'partner_id')
    def _compute_safex_intercompany_transfer(self):
        for move in self:
            company = (move.picking_id.company_id or move.company_id).sudo()
            partner = (move.picking_id.partner_id or move.partner_id).sudo().commercial_partner_id
            move.safex_intercompany_transfer = bool(
                company.partner_id.is_safex_internal_entity and partner.is_safex_internal_entity)

    def _safex_is_intercompany_purchase_move(self):
        """Move of an inter-company receipt (not a return): its serials must be the seller's."""
        self.ensure_one()
        picking = self.picking_id
        return bool(picking and picking.picking_type_id.code == 'incoming'
                    and picking._safex_is_purchase_move(self) and picking._safex_get_seller_company())

    def _should_bypass_reservation(self, forced_location=False):
        # CR-01: an inter-company receipt comes from the inter-company transit location, where old
        # quants of this company may lie (e.g. deliveries never received by the other company):
        # standard reservation would put those serials on the receipt. Its serials are loaded from the
        # seller's delivery or typed instead, so nothing is reserved there (lines without serial).
        # Context safex_standard_reservation: release reservations made before this rule existed.
        return super()._should_bypass_reservation(forced_location) or (
            not self.env.context.get('safex_standard_reservation')
            and self.product_id.tracking == 'serial' and self._safex_is_intercompany_purchase_move())

    def _safex_assign_received_lot(self, lot):
        """Put the serial ``lot`` on this receipt move: on a line without serial number, else on a new
        line, with its IMEIs and battery / docking station serials (entech_components_tracking fields)."""
        self.ensure_one()
        components = lot._safex_component_serials()
        lot_sudo = lot.sudo()
        vals = {
            'lot_id': lot.id,
            'lot_name': lot.name,
            'quantity': 1,
            'product_uom_id': self.product_id.uom_id.id,
            'imei_no_1': lot_sudo.imei_no_1 or False,
            'imei_no_2': lot_sudo.imei_no_2 or False,
            'battery_sno': components['battery'],
            'docking_station_sno': components['dock'],
            # Loaded = picked: on a partial load, validation puts the rest in a backorder.
            'picked': True,
        }
        free_line = self.move_line_ids.filtered(lambda ml: not ml.lot_id and not ml.lot_name)[:1]
        if free_line:
            free_line.write(vals)
        else:
            self.env['stock.move.line'].create(dict(self._prepare_move_line_vals(), **vals))

    def action_transfer_serial_fields(self):
        # Detailed Operations popup (entech_components_tracking) on an inter-company receipt: the serial
        # typed must be one the seller SafeX company delivered to this company and not received yet;
        # this company's serial is linked to the seller's one and brings its IMEIs and component serials.
        for move in self:
            picking = move.picking_id
            seller = picking._safex_get_seller_company() \
                if picking and move.serial_no and picking._safex_is_purchase_move(move) else None
            if not seller:
                continue
            source, buyer_lot = picking._safex_check_delivered_serial(seller, move.product_id, move.serial_no)
            lot = picking._safex_receive_seller_lot(source, move.product_id, buyer_lot).sudo()
            components = lot._safex_component_serials()
            move.write({
                'serial_no': lot.name,
                'imei_no_1': move.imei_no_1 or lot.imei_no_1,
                'imei_no_2': move.imei_no_2 or lot.imei_no_2,
                'battery_sno': move.battery_sno or components['battery'],
                'docking_station_sno': move.docking_station_sno or components['dock'],
            })
        return super().action_transfer_serial_fields()
