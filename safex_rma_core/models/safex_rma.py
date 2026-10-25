from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

RMA_STATES = [
    ('draft', "Draft"),
    ('submitted', "Submitted"),
    ('received', "Received"),
    ('inspection', "Inspection"),
    ('processing', "Processing"),
    ('dispatched', "Dispatched"),
    ('closed', "Closed"),
    ('cancel', "Cancelled"),
]

SHIPMENT_MODES = [
    ('air', "Air"),
    ('road', "Road"),
    ('sea', "Sea"),
]


class SafexRma(models.Model):
    """RMA shipment container: one dealer batch holding one or more devices."""
    _name = 'safex.rma'
    _description = "SafeX RMA"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string="RMA Reference", required=True, readonly=True, copy=False, default='New', index='trigram')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company,
        string="Operating Company")
    partner_id = fields.Many2one(
        'res.partner', string="Dealer", required=True, tracking=True, index=True,
        domain="[('is_company', '=', True)]")
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', store=True, index=True)
    user_id = fields.Many2one('res.users', string="Responsible", default=lambda self: self.env.user, tracking=True)
    state = fields.Selection(RMA_STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    line_ids = fields.One2many('safex.rma.line', 'rma_id', string="Devices", copy=True)
    device_count = fields.Integer(compute='_compute_device_count')
    submitted_date = fields.Datetime(readonly=True, copy=False)
    created_from_portal = fields.Boolean(readonly=True, copy=False)
    terms = fields.Html(
        string="Terms & Conditions",
        default=lambda self: self.env.company.safex_rma_terms)

    # Inbound logistics & carton (DES00107)
    received_date = fields.Datetime(tracking=True, copy=False)
    receiving_user_id = fields.Many2one('res.users', string="Receiving Staff", copy=False)
    shipment_mode = fields.Selection(SHIPMENT_MODES, string="Mode of Shipment")
    forwarder_id = fields.Many2one('res.partner', string="Forwarder / Courier", domain="[('is_company', '=', True)]")
    inbound_awb = fields.Char(string="Inbound AWB No.", tracking=True, index=True)
    customer_doc_ref = fields.Char(string="Customer Doc Ref", tracking=True)
    package_condition = fields.Selection([
        ('intact', "Intact"),
        ('damaged', "Damaged"),
        ('tampered', "Tampered"),
        ('water_damaged', "Water Damaged"),
    ], string="Carton State")
    package_photo_ids = fields.Many2many(
        'ir.attachment', 'safex_rma_package_photo_rel', 'rma_id', 'attachment_id', string="Carton Photos")
    receiving_remarks = fields.Text()

    # PO gating (DES00112): one PO number covers the whole RMA
    po_number = fields.Char(string="PO Number", tracking=True, copy=False)
    po_date = fields.Datetime(string="PO Received On", readonly=True, copy=False)
    po_pending_since = fields.Datetime(readonly=True, copy=False)
    has_po_pending = fields.Boolean(compute='_compute_line_flags', store=True)

    # Outbound logistics (BRD 9)
    outbound_shipment_mode = fields.Selection(SHIPMENT_MODES, string="Return Mode of Shipment")
    outbound_forwarder_id = fields.Many2one(
        'res.partner', string="Return Forwarder / Courier", domain="[('is_company', '=', True)]")
    outbound_awb = fields.Char(string="Outbound AWB No.", tracking=True)
    outbound_doc_ref = fields.Char(string="Return Document Ref")
    dispatch_date = fields.Datetime(readonly=True, copy=False)
    freight_payer = fields.Selection(
        [('factory', "Factory / SafeX"), ('partner', "Partner / Dealer")],
        string="Return Shipping Borne By", compute='_compute_freight_payer', store=True, readonly=False,
        tracking=True,
        help="Factory when any device has a manufacturing defect (regardless of warranty period); "
             "otherwise the dealer.")
    can_dispatch = fields.Boolean(compute='_compute_line_flags', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('safex.rma') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids')
    def _compute_device_count(self):
        for rma in self:
            rma.device_count = len(rma.line_ids)

    def _get_report_base_filename(self):
        # Used by the portal report download to name the PDF file.
        self.ensure_one()
        return self.name

    @api.depends('line_ids.state', 'line_ids.final_test_result', 'line_ids.quality_check')
    def _compute_line_flags(self):
        for rma in self:
            lines = rma.line_ids
            rma.has_po_pending = any(line.state == 'po_pending' for line in lines)
            rma.can_dispatch = bool(lines) and all(
                line.state == 'rejected'
                or (line.state == 'ready' and line.final_test_result == 'passed' and line.quality_check == 'passed')
                for line in lines
            )

    @api.depends('line_ids.is_manufacturing_defect')
    def _compute_freight_payer(self):
        for rma in self:
            rma.freight_payer = 'factory' if any(rma.line_ids.mapped('is_manufacturing_defect')) else 'partner'

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def action_submit(self):
        for rma in self:
            if rma.state != 'draft':
                raise UserError(self.env._("Only draft RMAs can be submitted."))
            if not rma.line_ids:
                raise UserError(self.env._("Add at least one device before submitting the RMA."))
            rma.write({'state': 'submitted', 'submitted_date': fields.Datetime.now()})
        return True

    def action_confirm_receipt(self):
        for rma in self:
            if rma.state != 'submitted':
                raise UserError(self.env._("Only submitted RMAs can be received."))
            if not rma.inbound_awb:
                raise UserError(self.env._("Enter the inbound AWB number before confirming receipt."))
            rma.write({
                'state': 'received',
                'received_date': fields.Datetime.now(),
                'receiving_user_id': self.env.user.id,
            })
            rma.message_post(body=self.env._(
                "Parcel received. Mode: %(mode)s, Forwarder: %(forwarder)s, AWB: %(awb)s, Customer Doc: %(doc)s",
                mode=dict(SHIPMENT_MODES).get(rma.shipment_mode, '-'),
                forwarder=rma.forwarder_id.display_name or '-',
                awb=rma.inbound_awb,
                doc=rma.customer_doc_ref or '-',
            ))
        return True

    def action_complete_physical_inspection(self):
        for rma in self:
            if rma.state != 'received':
                raise UserError(self.env._("The parcel must be received first."))
            pending = rma.line_ids.filtered(lambda line: line.state == 'draft')
            if pending:
                raise UserError(self.env._(
                    "Validate the physical inspection of every device first: %s",
                    ", ".join(pending.mapped('display_name'))))
            discrepancies = rma.line_ids.filtered('accessory_discrepancy')
            if discrepancies:
                rma.message_post(body=self.env._(
                    "Accessory discrepancy on: %s", ", ".join(discrepancies.mapped('display_name'))))
            rma.state = 'inspection'
        return True

    def _update_processing_state(self):
        """Move to processing once any device has passed technical inspection."""
        self.filtered(lambda rma: rma.state == 'inspection').state = 'processing'

    def action_submit_po(self, po_number=None):
        """Record the dealer's single PO number and unlock all PO-pending devices."""
        for rma in self:
            number = (po_number if po_number is not None else rma.po_number or '').strip()
            if not number:
                raise UserError(self.env._("The PO number cannot be empty."))
            rma.write({'po_number': number, 'po_date': fields.Datetime.now()})
            lines = rma.line_ids.filtered(lambda line: line.state == 'po_pending')
            lines.state = 'in_repair'
            rma.po_pending_since = False
            rma._update_processing_state()
            rma.message_post(body=self.env._(
                "PO %(po)s received. %(count)s device(s) released to repair.", po=number, count=len(lines)))
            technicians = lines.technician_id.partner_id
            if technicians:
                rma.message_subscribe(partner_ids=technicians.ids)
                rma.message_post(
                    body=self.env._("Repair work unblocked for PO %s.", number),
                    partner_ids=technicians.ids, subtype_xmlid='mail.mt_comment')
        return True

    def action_dispatch(self):
        for rma in self:
            if not rma.can_dispatch:
                raise ValidationError(self.env._(
                    "Cannot dispatch RMA. All devices must have a completed Final Test Result "
                    "and Quality Check before dispatch."))
            if not rma.outbound_awb:
                raise UserError(self.env._("Enter the outbound AWB number before dispatch."))
            rma.line_ids._consume_spare_parts()
            rma.write({'state': 'dispatched', 'dispatch_date': fields.Datetime.now()})
        return True

    def action_close(self):
        if any(rma.state != 'dispatched' for rma in self):
            raise UserError(self.env._("Only dispatched RMAs can be closed."))
        self.state = 'closed'
        return True

    def action_cancel(self):
        if any(rma.state in ('dispatched', 'closed') for rma in self):
            raise UserError(self.env._("Dispatched or closed RMAs cannot be cancelled."))
        self.state = 'cancel'
        return True

    def action_reset_draft(self):
        self.filtered(lambda rma: rma.state == 'cancel').state = 'draft'
        return True
