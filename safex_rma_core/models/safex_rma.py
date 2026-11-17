from odoo import Command, api, fields, models
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

# Domain of the RMA user dropdowns (Responsible, Receiving Staff, Technician, Inspector, QC):
# internal users of a SafeX group company only (CR-13).
SAFEX_USER_DOMAIN = [('share', '=', False), ('company_ids.partner_id.is_safex_internal_entity', '=', True)]

PO_STATUSES = [
    ('none', "Not Submitted"),
    ('submitted', "Awaiting Verification"),
    ('verified', "Verified"),
    ('rejected', "Rejected"),
]

SHIPMENT_MODES = [
    ('air', "Air"),
    ('road', "Road"),
    ('sea', "Sea"),
]


def _default_rma_company(env):
    """The company handling the RMAs of the current company (e.g. SafeX Qatar for SafeX UK) when the
    user may work in it, else the current company."""
    handler = env.company._get_safex_rma_company()
    return handler if handler in env.companies else env.company


class SafexRma(models.Model):
    """RMA shipment container: one dealer batch holding one or more devices."""
    _name = 'safex.rma'
    _description = "SafeX RMA"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string="RMA Reference", required=True, readonly=True, copy=False, default='New', index='trigram')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: _default_rma_company(self.env),
        string="Operating Company")
    partner_id = fields.Many2one(
        'res.partner', string="Dealer", required=True, tracking=True, index=True,
        domain="['|', ('is_safex_dealer', '=', True), ('commercial_partner_id.is_safex_dealer', '=', True)]")
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', store=True, index=True)
    user_id = fields.Many2one(
        'res.users', string="Responsible", default=lambda self: self.env.user, tracking=True,
        domain=SAFEX_USER_DOMAIN)
    state = fields.Selection(RMA_STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    line_ids = fields.One2many('safex.rma.line', 'rma_id', string="Devices", copy=True)
    device_count = fields.Integer(compute='_compute_device_count')
    submitted_date = fields.Datetime(readonly=True, copy=False)
    # CR-04: any SafeX device can be put on an RMA for any dealer; devices sold through another
    # dealer (or never sold to a dealer) are only flagged.
    has_other_dealer_device = fields.Boolean(
        string="Has Devices from Other Dealers", compute='_compute_has_other_dealer_device', store=True,
        help="At least one device was last sold through another dealer than this RMA's dealer.")
    # The other dealer may belong to another company than the user's: read in sudo.
    other_dealer_warning = fields.Text(compute='_compute_other_dealer_warning', compute_sudo=True)
    created_from_portal = fields.Boolean(readonly=True, copy=False)
    terms = fields.Html(
        string="Terms & Conditions",
        default=lambda self: _default_rma_company(self.env).safex_rma_terms)

    # Inbound logistics & carton (DES00107)
    received_date = fields.Datetime(tracking=True, copy=False)
    receiving_user_id = fields.Many2one(
        'res.users', string="Receiving Staff", copy=False, domain=SAFEX_USER_DOMAIN)
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
    po_document_ids = fields.Many2many(
        'ir.attachment', 'safex_rma_po_document_rel', 'rma_id', 'attachment_id',
        string="PO Documents", copy=False,
        help="Purchase Order documents of the current PO submission (uploaded by the dealer).")
    # Documents of PO submissions rejected by SafeX: kept for the history, never offered for verification.
    po_rejected_document_ids = fields.Many2many(
        'ir.attachment', 'safex_rma_po_rejected_document_rel', 'rma_id', 'attachment_id',
        string="Rejected PO Documents", copy=False, readonly=True)
    po_pending_since = fields.Datetime(readonly=True, copy=False)
    # PO verification (CR-09): the dealer's PO number is checked against the PO document by SafeX
    # before repair starts.
    po_status = fields.Selection(PO_STATUSES, string="PO Status", default='none', required=True,
                                 tracking=True, copy=False)
    po_rejection_reason = fields.Text(string="PO Rejection Reason", tracking=True, copy=False)
    po_verified_date = fields.Datetime(string="PO Verified On", readonly=True, copy=False)
    po_verified_user_id = fields.Many2one('res.users', string="PO Verified By", readonly=True, copy=False)
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
    # Notebook tab opened on the form: the one to fill in at the current stage.
    safex_stage_page = fields.Char(compute='_compute_safex_stage_page')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('safex.rma') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('po_number') and 'po_status' not in vals:
            # PO received outside the portal (e.g. by email): the number typed by SafeX staff on a
            # PO-pending RMA is a submission that still has to be verified against the document (CR-09).
            to_verify = self.filtered(lambda rma: rma.has_po_pending and rma.po_status in ('none', 'rejected'))
            if to_verify:
                to_verify.write({
                    'po_status': 'submitted',
                    'po_date': fields.Datetime.now(),
                    'po_rejection_reason': False,
                })
                to_verify._schedule_po_verification()
        return res

    @api.depends('line_ids')
    def _compute_device_count(self):
        for rma in self:
            rma.device_count = len(rma.line_ids)

    def _get_safex_responsible(self):
        """Internal user who receives SafeX follow-up activities (never the dealer's portal user)."""
        self.ensure_one()
        user = self.user_id
        if user and not user.share:
            return user
        return self.env.ref('base.user_admin', raise_if_not_found=False) or self.env['res.users'].browse()

    def _get_document_company(self):
        """Company whose letterhead, address and footer are printed on the RMA documents (CR-05)."""
        self.ensure_one()
        company = self.company_id.sudo()
        return company.safex_document_company_id or company

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        """Each RMA email reaches the dealer once: when the message is addressed to the RMA's dealer
        (partner_id, e.g. the mail templates' recipient), the dealer's other contacts that only follow
        the RMA (such as the portal user who created it) are not notified a second time."""
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        if len(self) != 1 or not self.partner_id:
            return recipients
        dealer = self.partner_id
        if dealer.id not in [recipient['id'] for recipient in recipients]:
            return recipients
        explicit_ids = set(msg_vals.get('partner_ids') or [] if msg_vals else message.sudo().partner_ids.ids)
        commercial = dealer.commercial_partner_id
        partners = self.env['res.partner'].sudo().browse(
            [recipient['id'] for recipient in recipients if recipient['id']])
        dealer_side = set(partners.filtered(lambda partner: partner.commercial_partner_id == commercial).ids)
        return [
            recipient for recipient in recipients
            if recipient['id'] == dealer.id or recipient['id'] in explicit_ids or recipient['id'] not in dealer_side
        ]

    def _get_report_base_filename(self):
        # Used by the portal report download to name the PDF file.
        self.ensure_one()
        return self.name

    @api.depends('line_ids.state', 'line_ids.final_test_result', 'line_ids.quality_check', 'line_ids.not_received')
    def _compute_line_flags(self):
        for rma in self:
            # Devices that never arrived are not part of the repair or of the return shipment.
            lines = rma.line_ids.filtered(lambda line: not line.not_received)
            rma.has_po_pending = any(line.state == 'po_pending' for line in lines)
            rma.can_dispatch = bool(lines) and all(
                line.state == 'rejected'
                or (line.state == 'ready' and line.final_test_result == 'passed' and line.quality_check == 'passed')
                for line in lines
            )

    @api.depends('state', 'has_po_pending', 'can_dispatch')
    def _compute_safex_stage_page(self):
        for rma in self:
            rma.safex_stage_page = rma._get_safex_stage_page()

    def _get_safex_stage_page(self):
        """Name of the form's notebook page to fill in at the RMA's current stage."""
        self.ensure_one()
        if self.state == 'submitted':
            return 'inbound'  # parcel arrival: freight, AWB, carton condition
        if self.state in ('dispatched', 'closed') or (self.state in ('inspection', 'processing') and self.can_dispatch):
            return 'dispatch'
        if self.has_po_pending:
            return 'po'
        return 'devices'

    @api.depends('line_ids.is_manufacturing_defect')
    def _compute_freight_payer(self):
        for rma in self:
            rma.freight_payer = 'factory' if any(rma.line_ids.mapped('is_manufacturing_defect')) else 'partner'

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    @api.depends('line_ids.sold_through_other_dealer')
    def _compute_has_other_dealer_device(self):
        for rma in self:
            rma.has_other_dealer_device = any(rma.line_ids.mapped('sold_through_other_dealer'))

    @api.depends('line_ids.sold_through_other_dealer', 'line_ids.channel_distributor_id')
    def _compute_other_dealer_warning(self):
        for rma in self:
            rma.other_dealer_warning = "\n".join(
                self.env._("%(serial)s: sold through %(distributor)s",
                           serial=line.lot_id.name, distributor=line.channel_distributor_id.sudo().display_name)
                for line in rma.line_ids.filtered('sold_through_other_dealer')) or False

    def action_submit(self):
        for rma in self:
            if rma.state != 'draft':
                raise UserError(self.env._("Only draft RMAs can be submitted."))
            if not rma.line_ids:
                raise UserError(self.env._("Add at least one device before submitting the RMA."))
            rma.write({'state': 'submitted', 'submitted_date': fields.Datetime.now()})
            # CR-04: devices sold through another dealer are noted once, at submission (the dealer and
            # the devices can still change while the RMA is a draft).
            rma.line_ids._safex_log_other_dealer_devices()
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
            # A device declared by the dealer but missing from the carton does not block the inspection.
            missing = rma.line_ids.filtered('not_received')
            pending = rma.line_ids.filtered(lambda line: line.state == 'draft') - missing
            if pending:
                raise UserError(self.env._(
                    "Validate the physical inspection of every device first: %s",
                    ", ".join(pending.mapped('display_name'))))
            if missing == rma.line_ids:
                raise UserError(self.env._(
                    "Every device is marked as Not Received: there is nothing to inspect."))
            if missing:
                rma.message_post(body=self.env._(
                    "Declared but not received: %s", ", ".join(missing.mapped('display_name'))))
            discrepancies = rma.line_ids.filtered('accessory_discrepancy')
            if discrepancies:
                rma.message_post(body=self.env._(
                    "Accessory discrepancy on: %s", ", ".join(discrepancies.mapped('display_name'))))
            rma.state = 'inspection'
        return True

    def _update_processing_state(self):
        """Move to processing once any device has passed technical inspection."""
        self.filtered(lambda rma: rma.state == 'inspection').state = 'processing'

    @staticmethod
    def _normalize_po_number(number):
        """PO numbers are compared ignoring case and spaces."""
        return ''.join((number or '').split()).casefold()

    def _get_po_verification_activities(self):
        prefix = self.env._("Verify PO %s", '').strip()
        return self.activity_ids.filtered(lambda activity: (activity.summary or '').startswith(prefix))

    def _schedule_po_verification(self):
        for rma in self:
            # A resubmitted PO replaces the previous verification request.
            rma._get_po_verification_activities().unlink()
            rma.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=self.env._("Verify PO %s", rma.po_number),
                note=self.env._("Check the PO number against the PO document received, then click Verify PO "
                                "(or Reject PO)."),
                user_id=rma._get_safex_responsible().id)

    def _close_po_verification_activities(self, feedback):
        self._get_po_verification_activities().action_feedback(feedback=feedback)

    def action_dealer_submit_po(self, po_number, attachments=None, author=None):
        """The dealer entered the PO number (and sent the PO document): it waits for SafeX's
        verification, repair does not start yet (CR-09)."""
        number = (po_number or '').strip()
        if not number:
            raise UserError(self.env._("The PO number cannot be empty."))
        for rma in self:
            if not rma.has_po_pending:
                raise UserError(self.env._("%s is not waiting for a PO.", rma.name))
            if rma.po_status == 'verified':
                raise UserError(self.env._("The PO of %s has already been verified.", rma.name))
            rma.write({
                'po_number': number,
                'po_date': fields.Datetime.now(),
                'po_status': 'submitted',
                'po_rejection_reason': False,
            })
            # Only the documents of this submission are offered for verification (none when the
            # dealer sends the PO document by email).
            rma.po_document_ids = [Command.set(attachments.ids if attachments else [])]
            rma.message_post(
                body=self.env._("PO %s submitted by the dealer, awaiting verification.", number),
                attachment_ids=attachments.ids if attachments else [],
                author_id=(author or rma.partner_id).id)
            rma._schedule_po_verification()
        return True

    def action_open_po_verify_wizard(self):
        self.ensure_one()
        if not self.has_po_pending or self.po_status != 'submitted':
            raise UserError(self.env._("%s has no PO awaiting verification.", self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Verify PO"),
            'res_model': 'safex.rma.po.verify',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_rma_id': self.id},
        }

    def action_open_po_reject_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Reject PO"),
            'res_model': 'safex.rma.po.reject',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_rma_id': self.id},
        }

    def action_verify_po(self, po_number):
        """Staff typed the PO number read on the PO document: it must match the dealer's number.
        On success the PO-pending devices are released to repair."""
        self.ensure_one()
        typed = (po_number or '').strip()
        if not typed:
            raise UserError(self.env._("Enter the PO number shown on the PO document."))
        if not self.has_po_pending:
            raise UserError(self.env._("No device of %s is waiting for a PO.", self.name))
        if self.po_status == 'verified':
            raise UserError(self.env._("The PO of %s has already been verified.", self.name))
        if self.po_status != 'submitted':
            # Not submitted yet, or rejected: the dealer (or staff, by entering the PO number) must
            # submit a PO before it can be verified.
            raise UserError(self.env._("%s has no PO awaiting verification.", self.name))
        if self.po_number and self._normalize_po_number(typed) != self._normalize_po_number(self.po_number):
            raise UserError(self.env._(
                "PO number %(typed)s does not match the number entered by the dealer (%(dealer)s). "
                "Check the PO document, or reject the PO with a reason.", typed=typed, dealer=self.po_number))
        self.write({
            'po_number': self.po_number or typed,
            'po_status': 'verified',
            'po_rejection_reason': False,
            'po_verified_date': fields.Datetime.now(),
            'po_verified_user_id': self.env.user.id,
        })
        self._close_po_verification_activities(self.env._("PO verified"))
        self.message_post(body=self.env._("PO %s verified against the PO document.", self.po_number))
        return self.action_submit_po(self.po_number)

    def action_reject_po(self, reason):
        """The PO document does not match / is not acceptable: the dealer must submit it again."""
        reason = (reason or '').strip()
        if not reason:
            raise UserError(self.env._("A reason is mandatory to reject the PO."))
        for rma in self:
            if rma.po_status != 'submitted':
                raise UserError(self.env._("%s has no PO awaiting verification.", rma.name))
            rma.write({
                'po_status': 'rejected',
                'po_rejection_reason': reason,
                # The rejected documents leave the current submission (kept as history).
                'po_rejected_document_ids': [Command.link(doc.id) for doc in rma.po_document_ids],
                'po_document_ids': [Command.clear()],
            })
            rma._close_po_verification_activities(self.env._("PO rejected: %s", reason))
            rma.message_post(
                body=self.env._(
                    "PO %(po)s was not accepted. Reason: %(reason)s. Please submit a corrected PO on the "
                    "dealer portal.", po=rma.po_number, reason=reason),
                partner_ids=rma.partner_id.ids, message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    def action_submit_po(self, po_number=None):
        """Release logic once the PO is verified: record the PO number and unlock all PO-pending devices."""
        for rma in self:
            number = (po_number if po_number is not None else rma.po_number or '').strip()
            if not number:
                raise UserError(self.env._("The PO number cannot be empty."))
            if rma.po_status != 'verified':
                raise UserError(self.env._("Verify the PO of %s before releasing the devices to repair.", rma.name))
            rma.write({'po_number': number, 'po_date': rma.po_date or fields.Datetime.now()})
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
                    # Internal note: only the mentioned technicians are notified, never the
                    # dealer's portal contacts that follow the RMA with the Discussions subtype.
                    partner_ids=technicians.ids, subtype_xmlid='mail.mt_note')
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
        rmas = self.filtered(lambda rma: rma.state == 'cancel')
        rmas.state = 'draft'
        # The serials may have been put on another RMA while this one was cancelled.
        rmas.line_ids._check_open_rma_duplicates()
        return True
