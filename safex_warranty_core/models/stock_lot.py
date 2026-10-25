from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

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

    warranty_classification = fields.Selection(
        WARRANTY_CLASSIFICATION, tracking=True, groups='base.group_user',
        help="Last classification confirmed at technical inspection.")

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

    @api.model
    def verify_device_for_portal(self, serial_no, imei, dealer_partner_id):
        """Cross-company verification for the dealer portal (DES00104).

        Returns only {'verified', 'lot_id', 'product_name'} on success. Never exposes
        stock, locations, costs or warranty data.
        """
        failure = {
            'verified': False,
            'message': self.env._(
                "Device verification failed. Serial Number or IMEI combination "
                "not found in your delivered purchases."),
        }
        serial_no = (serial_no or '').strip()
        imei = (imei or '').strip()
        if not serial_no or not imei:
            return failure
        dealer = self.env['res.partner'].sudo().browse(dealer_partner_id).exists()
        if not dealer:
            return failure
        lots = self.sudo().with_context(active_test=False).search([
            ('name', '=', serial_no),
            '|', ('imei_no_1', '=', imei), ('imei_no_2', '=', imei),
        ])
        for lot in lots:
            move_lines = lot._get_dealer_delivery_move_lines(dealer)
            if move_lines:
                if not lot.dealer_delivery_date:
                    lot.dealer_delivery_date = fields.Date.to_date(move_lines[-1].date)
                return {
                    'verified': True,
                    'lot_id': lot.id,
                    'product_name': lot.product_id.display_name,
                }
        return failure
