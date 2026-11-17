from odoo import api, fields, models
from odoo.exceptions import UserError


class SafexRma(models.Model):
    _inherit = 'safex.rma'

    sale_order_ids = fields.One2many('sale.order', 'rma_id', string="Quotations")
    quotation_count = fields.Integer(compute='_compute_sale_info')
    invoice_ids = fields.Many2many('account.move', compute='_compute_sale_info', string="Invoices")
    invoice_count = fields.Integer(compute='_compute_sale_info')
    amount_total = fields.Monetary(compute='_compute_sale_info', string="Quoted Total", currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    quote_sent_date = fields.Datetime(tracking=True, copy=False, readonly=True)
    has_quoted_lines = fields.Boolean(compute='_compute_has_quoted_lines')
    has_quotation_to_approve = fields.Boolean(compute='_compute_button_flags')
    has_amount_to_invoice = fields.Boolean(compute='_compute_button_flags')
    po_pending_days = fields.Integer(compute='_compute_po_pending_days')
    last_reminder_day = fields.Integer(copy=False, readonly=True)

    @api.depends('sale_order_ids.state', 'sale_order_ids.amount_total', 'sale_order_ids.invoice_ids')
    def _compute_sale_info(self):
        for rma in self:
            orders = rma.sale_order_ids.filtered(lambda so: so.state != 'cancel')
            rma.quotation_count = len(orders)
            rma.invoice_ids = orders.invoice_ids
            rma.invoice_count = len(rma.invoice_ids)
            rma.amount_total = sum(orders.mapped('amount_total'))

    @api.depends('sale_order_ids.state', 'sale_order_ids.invoice_status', 'sale_order_ids.amount_total',
                 'has_po_pending')
    def _compute_button_flags(self):
        # Same conditions as action_dealer_approve / action_create_invoice, so the buttons
        # only show when clicking them can succeed.
        for rma in self:
            orders = rma.sale_order_ids
            rma.has_quotation_to_approve = any(so.state in ('draft', 'sent', 'to_approve') for so in orders)
            # Nothing is invoiced while devices still wait for the dealer's PO (or its verification).
            rma.has_amount_to_invoice = not rma.has_po_pending and bool(orders._safex_filter_to_invoice())

    @api.depends('line_ids.state', 'line_ids.sale_line_ids')
    def _compute_has_quoted_lines(self):
        for rma in self:
            rma.has_quoted_lines = any(line.state == 'quoted' and not line.sale_line_ids for line in rma.line_ids)

    @api.depends('po_pending_since')
    def _compute_po_pending_days(self):
        now = fields.Datetime.now()
        for rma in self:
            rma.po_pending_days = (now - rma.po_pending_since).days if rma.po_pending_since else 0

    # ------------------------------------------------------------------
    # Quotation
    # ------------------------------------------------------------------

    def _get_service_charge_product(self):
        return self.env.ref('safex_rma_sale_account.product_repair_service_charge')

    def _prepare_quotation_lines(self, devices):
        service_product = self._get_service_charge_product()
        commands = []
        # Units of the same model are kept together so that the documents can print the model once
        # with each unit's serial number beneath it (CR-06).
        devices = devices.sorted(lambda device: (device.product_id.display_name or '', device.sequence, device.id))
        for device in devices:
            imei = f" (IMEI: {device.imei_1})" if device.imei_1 else ""
            commands.append(fields.Command.create({
                'display_type': 'line_section',
                'name': f"{device.product_id.display_name} - S/N: {device.lot_id.name}{imei}",
                'rma_line_id': device.id,
            }))
            # Warranty / manufacturing-defect repairs are quoted at 0.00 (CR-08). The wording never
            # mentions the warranty decision: dealers do not see warranty details.
            if device.is_chargeable:
                name = self.env._("Repair Service Charge - %(report)s", report=device.dealer_facing_report or '')
            else:
                name = self.env._("Repair Service (No Charge) - %(report)s", report=device.dealer_facing_report or '')
            commands.append(fields.Command.create({
                'product_id': service_product.id,
                'name': name,
                'product_uom_qty': 1.0,
                'price_unit': device.service_charge_amount if device.is_chargeable else 0.0,
                'rma_line_id': device.id,
                'is_service_charge': True,
            }))
            for part in device.part_line_ids:
                commands.append(fields.Command.create({
                    'product_id': part.product_id.id,
                    'name': self.env._("%s [Replaced Part - Cost Absorbed in Service Charge]",
                                       part.product_id.display_name),
                    'product_uom_qty': part.quantity,
                    'price_unit': 0.0,
                    'rma_line_id': device.id,
                    'rma_part_id': part.id,
                    'is_spare_part': True,
                }))
        return commands

    def action_generate_quotation(self):
        """Create one sectioned quotation for the devices not quoted yet: chargeable devices at their
        service charge, warranty / manufacturing-defect devices at 0.00 (CR-08)."""
        self.ensure_one()
        devices = self.line_ids.filtered(lambda line: line.state == 'quoted' and not line.sale_line_ids)
        if not devices:
            raise UserError(self.env._("No device is waiting for a quotation."))
        missing_price = devices.filtered(lambda line: line.is_chargeable and line.service_charge_amount <= 0)
        if missing_price:
            raise UserError(self.env._(
                "Set the Repair Service Charge on: %s", ", ".join(missing_price.mapped('display_name'))))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'rma_id': self.id,
            'origin': self.name,
            'client_order_ref': self.po_number or False,
            'Customer_Purchase': self.po_number or False,
            'Customer_Purchase_date': self.po_date.date() if self.po_number and self.po_date else False,
            'note': self.company_id.safex_quotation_terms or False,
            'order_line': self._prepare_quotation_lines(devices),
        })
        return self._open_orders(order)

    def action_send_quotation(self):
        """Publish the open quotations to the dealer portal."""
        self.ensure_one()
        drafts = self.sale_order_ids.filtered(lambda so: so.state == 'draft')
        if not drafts:
            raise UserError(self.env._("There is no draft quotation to send."))
        drafts.action_quotation_sent()
        self.quote_sent_date = fields.Datetime.now()
        self.message_post(body=self.env._(
            "Quotation %s published to the dealer portal.", ", ".join(drafts.mapped('name'))))
        return True

    def action_dealer_approve(self):
        """Dealer accepted the quotation: devices wait for the PO number (BRD 7)."""
        for rma in self:
            orders = rma.sale_order_ids.filtered(lambda so: so.state in ('draft', 'sent', 'to_approve'))
            if not orders:
                raise UserError(self.env._("There is no quotation awaiting approval."))
            orders.action_confirm()
            unconfirmed = orders.filtered(lambda so: so.state != 'sale')
            if unconfirmed:
                raise UserError(self.env._(
                    "Quotation %s needs a price approval before it can be approved.",
                    ", ".join(unconfirmed.mapped('name'))))
            devices = orders.order_line.rma_line_id._set_po_pending()
            rma.message_post(body=self.env._(
                "Quotation %(orders)s approved by the dealer. %(count)s device(s) now PO Pending.",
                orders=", ".join(orders.mapped('name')), count=len(devices)))
            # No "PO required" notice when the dealer's PO is already with SafeX for verification.
            if rma.has_po_pending and rma.po_status in ('none', 'rejected'):
                template = self.env.ref('safex_rma_sale_account.mail_template_po_pending', raise_if_not_found=False)
                if template:
                    rma.message_post_with_source(template, subtype_xmlid='mail.mt_comment')
        return True

    def action_dealer_request_clarification(self, reason, author=None):
        reason = (reason or '').strip()
        if not reason:
            raise UserError(self.env._("A reason is mandatory to request a clarification."))
        for rma in self:
            rma.message_post(
                body=self.env._("Clarification requested by dealer: %s", reason),
                author_id=(author or rma.partner_id).id,
                message_type='comment', subtype_xmlid='mail.mt_comment')
            rma.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=self.env._("Dealer clarification requested"),
                note=reason,
                user_id=rma._get_safex_responsible().id)
        return True

    def action_dealer_submit_po(self, po_number, attachments=None, author=None):
        """Also email the PO (number + document) to the company's PO mailbox (CR-09)."""
        res = super().action_dealer_submit_po(po_number, attachments=attachments, author=author)
        template = self.env.ref('safex_rma_sale_account.mail_template_po_submitted', raise_if_not_found=False)
        if not template:
            return res
        for rma in self:
            mailbox = rma.company_id._get_safex_po_email()
            if not mailbox:
                rma.message_post(body=self.env._(
                    "PO %(po)s could not be emailed: set the PO Email Address (or an email) on company %(company)s.",
                    po=rma.po_number, company=rma.company_id.name))
                continue
            template.send_mail(rma.id, email_values={
                'email_to': mailbox,
                'attachment_ids': attachments.ids if attachments else [],
            })
            rma.message_post(body=self.env._("PO %(po)s emailed to %(mailbox)s.", po=rma.po_number, mailbox=mailbox))
        return res

    def action_submit_po(self, po_number=None):
        res = super().action_submit_po(po_number)
        for rma in self:
            rma.sale_order_ids.filtered(lambda so: so.state != 'cancel').write({
                'client_order_ref': rma.po_number,
                'Customer_Purchase': rma.po_number,
                'Customer_Purchase_date': fields.Date.to_date(rma.po_date),
            })
        self.last_reminder_day = 0
        return res

    # ------------------------------------------------------------------
    # Invoicing
    # ------------------------------------------------------------------

    def action_create_invoice(self):
        self.ensure_one()
        if self.has_po_pending:
            raise UserError(self.env._(
                "%s: devices are still waiting for the PO (or its verification). Invoice once the PO is verified.",
                self.name))
        orders = self.sale_order_ids._safex_filter_to_invoice()
        if not orders:
            raise UserError(self.env._("There is nothing to invoice on this RMA."))
        invoices = orders._create_invoices()
        return self.action_view_invoices(invoices)

    def action_dispatch(self):
        """BRD 9 (Final Test -> QC -> Invoice -> Dispatch): an approved repair quotation must be
        invoiced, and the invoice posted, before the devices are dispatched. A 0.00 quotation
        (warranty / manufacturing-defect repairs, CR-08) needs no invoice."""
        for rma in self.filtered('can_dispatch'):
            orders = rma.sale_order_ids.filtered(lambda so: so.state == 'sale')
            uninvoiced = orders._safex_filter_to_invoice()
            if uninvoiced:
                raise UserError(self.env._(
                    "Create the invoice for %(orders)s before dispatching %(rma)s.",
                    orders=", ".join(uninvoiced.mapped('name')), rma=rma.name))
            drafts = orders.invoice_ids.filtered(lambda move: move.state == 'draft')
            if drafts:
                raise UserError(self.env._(
                    "Post invoice %(invoices)s before dispatching %(rma)s.",
                    invoices=", ".join(drafts.mapped('display_name')), rma=rma.name))
        return super().action_dispatch()

    def action_view_quotations(self):
        self.ensure_one()
        return self._open_orders(self.sale_order_ids)

    def action_view_invoices(self, invoices=None):
        self.ensure_one()
        return self.sale_order_ids.action_view_invoice(invoices if invoices is not None else self.invoice_ids)

    def _open_orders(self, orders):
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        if len(orders) == 1:
            action.update({'views': [(False, 'form')], 'res_id': orders.id})
        else:
            action['domain'] = [('id', 'in', orders.ids)]
        return action

    # ------------------------------------------------------------------
    # PO pending reminders (never closes the quotation)
    # ------------------------------------------------------------------

    @api.model
    def _cron_send_po_pending_reminders(self):
        template = self.env.ref('safex_rma_sale_account.mail_template_po_reminder', raise_if_not_found=False)
        if not template:
            return
        # No reminder while the dealer's PO waits for SafeX's verification; they resume if it is rejected.
        for rma in self.search([
            ('has_po_pending', '=', True),
            ('po_pending_since', '!=', False),
            ('po_status', 'in', ('none', 'rejected')),
        ]):
            days = rma.po_pending_days
            milestones = [day for day in rma.company_id._get_safex_po_reminder_days()
                          if rma.last_reminder_day < day <= days]
            if not milestones:
                continue
            rma.message_post_with_source(template, subtype_xmlid='mail.mt_comment')
            rma.last_reminder_day = milestones[-1]
