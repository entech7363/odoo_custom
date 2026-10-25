from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.safex_warranty_core.models.stock_lot import WARRANTY_CLASSIFICATION

LINE_STATES = [
    ('draft', "Draft"),
    ('inspected', "Inspected"),
    ('quoted', "Quoted"),
    ('po_pending', "PO Pending"),
    ('in_repair', "In Repair"),
    ('qc_testing', "QC Testing"),
    ('ready', "Ready"),
    ('rejected', "Rejected / Return As-Is"),
]

CHARGEABLE_CLASSIFICATIONS = ('out_of_warranty', 'warranty_rejected', 'physical_damage', 'replacement_recommended')

ACCESSORIES = ['charger', 'dock', 'battery', 'screwdriver', 'cable', 'box']

TEST_RESULTS = [
    ('pending', "Pending"),
    ('passed', "Passed"),
    ('failed', "Failed"),
]


class SafexRmaLine(models.Model):
    """One device (serial number) inside an RMA."""
    _name = 'safex.rma.line'
    _description = "SafeX RMA Device"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'rma_id desc, sequence, id'
    _check_company_auto = True

    rma_id = fields.Many2one('safex.rma', string="RMA", required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related='rma_id.company_id', store=True, index=True)
    partner_id = fields.Many2one(related='rma_id.partner_id', store=True, index=True, string="Dealer")
    state = fields.Selection(LINE_STATES, default='draft', required=True, tracking=True, copy=False, index=True)

    # Device identity
    lot_id = fields.Many2one('stock.lot', string="Serial Number", required=True, index=True)
    product_id = fields.Many2one(related='lot_id.product_id', store=True, string="Device Model")
    imei_1 = fields.Char(related='lot_id.imei_1', string="IMEI 1")
    imei_2 = fields.Char(related='lot_id.imei_2', string="IMEI 2")
    end_customer_name = fields.Char(string="Customer Name")
    end_customer_company = fields.Char(string="Customer Company")
    complaint_description = fields.Text(string="Complaint", required=True)
    complaint_photo_ids = fields.Many2many(
        'ir.attachment', 'safex_rma_line_complaint_photo_rel', 'line_id', 'attachment_id',
        string="Complaint Photos", help="Optional: photos may also be sent by email.")

    # Accessories: declared by dealer vs received by SafeX (DES00107)
    acc_declared_charger = fields.Boolean(string="Charger")
    acc_declared_dock = fields.Boolean(string="Docking Station")
    acc_declared_battery = fields.Boolean(string="Battery")
    acc_declared_screwdriver = fields.Boolean(string="Screwdriver")
    acc_declared_cable = fields.Boolean(string="Cable")
    acc_declared_box = fields.Boolean(string="With Box")
    acc_declared_other = fields.Char(string="Other (Declared)")
    acc_received_charger = fields.Boolean(string="Charger Received")
    acc_received_dock = fields.Boolean(string="Docking Station Received")
    acc_received_battery = fields.Boolean(string="Battery Received")
    acc_received_screwdriver = fields.Boolean(string="Screwdriver Received")
    acc_received_cable = fields.Boolean(string="Cable Received")
    acc_received_box = fields.Boolean(string="Box Received")
    acc_received_other = fields.Char(string="Other (Received)")
    accessory_discrepancy = fields.Boolean(compute='_compute_accessory_discrepancy', store=True)
    accessory_notes = fields.Text()
    is_unexpected_device = fields.Boolean(
        string="Unexpected Device", help="Found in the carton but not declared on the RMA.")

    # Physical inspection (DES00108)
    physical_inspector_id = fields.Many2one('res.users', string="Inspector", copy=False)
    physical_inspection_date = fields.Datetime(copy=False)
    # Configurable checklist: RMA & Repairs > Configuration > Inspection Checklist
    inspection_line_ids = fields.One2many(
        'safex.rma.line.inspection', 'rma_line_id', string="Inspection Checklist", copy=False)
    physical_inspection_notes = fields.Text()
    inspection_photo_ids = fields.Many2many(
        'ir.attachment', 'safex_rma_line_inspection_photo_rel', 'line_id', 'attachment_id',
        string="Inspection Photos")
    physical_damage_suspected = fields.Boolean(
        compute='_compute_physical_damage_suspected', store=True,
        help="A checklist option flagged 'Damage - Photo Required' was chosen.")

    # Repeat device (snapshot taken when the serial is selected)
    is_repeat_device = fields.Boolean(compute='_compute_repeat_device_info', store=True)
    last_repair_date = fields.Date(compute='_compute_repeat_device_info', store=True, string="Previous Repair Date")
    last_rma_number = fields.Char(compute='_compute_repeat_device_info', store=True, string="Previous RMA")
    repeat_repair_warning = fields.Char(compute='_compute_repeat_repair_warning')

    # Warranty (internal only)
    dealer_warranty_expiry = fields.Date(
        compute='_compute_warranty_info', groups='base.group_user', string="Dealer Warranty Expiry")
    factory_warranty_expiry = fields.Date(
        compute='_compute_warranty_info', groups='base.group_user', string="Factory Warranty Expiry")
    under_dealer_warranty = fields.Boolean(compute='_compute_warranty_info', groups='base.group_user')

    # Technical inspection & warranty decision (DES00109, DES00110)
    technician_id = fields.Many2one('res.users', string="Technician", tracking=True)
    diagnostic_date = fields.Datetime(tracking=True, copy=False)
    diagnostic_hours = fields.Float(default=1.0)
    fault_category = fields.Selection([
        ('motherboard', "Motherboard / Power"),
        ('display', "Display"),
        ('battery', "Battery"),
        ('rf_connectivity', "RF / Connectivity"),
        ('audio_mic', "Audio / Microphone"),
        ('camera', "Camera"),
        ('housing_seal', "Housing / ATEX Seal"),
        ('software_os', "Software / OS"),
    ])
    warranty_classification = fields.Selection(WARRANTY_CLASSIFICATION, tracking=True)
    is_manufacturing_defect = fields.Boolean(
        tracking=True,
        help="Genuine manufacturing defect: return shipping is borne by the factory, "
             "even outside the warranty period.")
    is_chargeable = fields.Boolean(compute='_compute_is_chargeable', store=True)
    warranty_decision_notes = fields.Text()
    internal_tech_notes = fields.Text(string="Internal Engineering Notes", groups='base.group_user')
    dealer_facing_report = fields.Text(string="Dealer Diagnostic Report", tracking=True)

    # Repair execution (DES00111)
    part_line_ids = fields.One2many('safex.rma.line.part', 'rma_line_id', string="Spare Parts", copy=False)
    repair_date = fields.Date(tracking=True, copy=False)
    repair_work_done = fields.Text(tracking=True)
    repair_notes = fields.Text(groups='base.group_user')

    # Final test & quality check (DES00113)
    final_test_result = fields.Selection(TEST_RESULTS, default='pending', tracking=True, copy=False)
    final_test_notes = fields.Text()
    quality_check = fields.Selection(TEST_RESULTS, default='pending', tracking=True, copy=False)
    quality_check_user_id = fields.Many2one('res.users', string="Quality Checked By", copy=False)
    quality_check_date = fields.Datetime(copy=False)

    rejection_reason = fields.Text(tracking=True, copy=False)

    @api.depends('rma_id.name', 'lot_id.name', 'product_id')
    def _compute_display_name(self):
        for line in self:
            line.display_name = f"{line.rma_id.name or ''} - {line.product_id.name or ''} [{line.lot_id.name or ''}]"

    @api.depends(*[f'acc_declared_{acc}' for acc in ACCESSORIES], *[f'acc_received_{acc}' for acc in ACCESSORIES],
                 'acc_declared_other', 'acc_received_other')
    def _compute_accessory_discrepancy(self):
        for line in self:
            missing = any(line[f'acc_declared_{acc}'] and not line[f'acc_received_{acc}'] for acc in ACCESSORIES)
            line.accessory_discrepancy = missing or bool(line.acc_declared_other and not line.acc_received_other)

    @api.depends('inspection_line_ids.option_id.requires_photo')
    def _compute_physical_damage_suspected(self):
        for line in self:
            line.physical_damage_suspected = any(line.inspection_line_ids.option_id.mapped('requires_photo'))

    @api.depends('lot_id')
    def _compute_repeat_device_info(self):
        for line in self:
            lot = line.lot_id
            line.last_repair_date = lot.last_repair_date
            line.last_rma_number = lot.last_rma_number
            line.is_repeat_device = bool(lot.last_repair_date or lot.last_rma_number)

    @api.depends('is_repeat_device', 'last_repair_date', 'last_rma_number')
    def _compute_repeat_repair_warning(self):
        for line in self:
            if line.is_repeat_device:
                line.repeat_repair_warning = self.env._(
                    "Warning: this device was previously serviced on %(date)s under %(rma)s",
                    date=line.last_repair_date or '-', rma=line.last_rma_number or '-')
            else:
                line.repeat_repair_warning = False

    @api.depends('lot_id')
    def _compute_warranty_info(self):
        for line in self:
            lot = line.lot_id.sudo()
            line.dealer_warranty_expiry = lot.dealer_warranty_expiry
            line.factory_warranty_expiry = lot.factory_warranty_expiry
            line.under_dealer_warranty = bool(lot) and lot._is_under_dealer_warranty()

    @api.depends('warranty_classification')
    def _compute_is_chargeable(self):
        for line in self:
            line.is_chargeable = line.warranty_classification in CHARGEABLE_CLASSIFICATIONS

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_inspection_lines()
        return lines

    def _sync_inspection_lines(self):
        """Add the active checklist items a device does not have yet, pre-filled with their default option."""
        items = self.env['safex.inspection.item'].search([])
        commands_by_line = {}
        for line in self:
            missing = items - line.inspection_line_ids.item_id
            if missing:
                commands_by_line[line] = [
                    fields.Command.create({'item_id': item.id, 'option_id': item.default_option_id.id})
                    for item in missing
                ]
        for line, commands in commands_by_line.items():
            line.sudo().inspection_line_ids = commands

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def action_validate_physical_inspection(self):
        for line in self:
            if line.state != 'draft':
                continue
            line._sync_inspection_lines()
            missing = line.inspection_line_ids.filtered(
                lambda result: result.item_id.active and result.item_id.required and not result.option_id
            ).item_id.mapped('name')
            if missing:
                raise UserError(self.env._(
                    "%(device)s: complete the inspection checklist (%(fields)s).",
                    device=line.display_name, fields=", ".join(missing)))
            if line.physical_damage_suspected and not line.inspection_photo_ids:
                raise UserError(self.env._(
                    "%s: attach at least one photo documenting the physical damage.", line.display_name))
            vals = {
                'state': 'inspected',
                'physical_inspector_id': line.physical_inspector_id.id or self.env.user.id,
                'physical_inspection_date': fields.Datetime.now(),
            }
            if not line.warranty_classification:
                suggested = line.inspection_line_ids.option_id.filtered('suggested_classification')[:1]
                if suggested:
                    vals['warranty_classification'] = suggested.suggested_classification
            line.write(vals)
        return True

    def action_validate_technical_inspection(self):
        """Route each device: free repair, quotation (chargeable) or return as-is (NFF)."""
        for line in self:
            if line.state != 'inspected':
                raise UserError(self.env._("%s: physical inspection must be validated first.", line.display_name))
            if line.rma_id.state not in ('inspection', 'processing'):
                raise UserError(self.env._("%s: complete the RMA physical inspection first.", line.display_name))
            required = ['technician_id', 'warranty_classification', 'dealer_facing_report']
            if line.warranty_classification != 'no_fault_found':
                required.append('fault_category')
            missing = [line._fields[f].string for f in required if not line[f]]
            if missing:
                raise UserError(self.env._(
                    "%(device)s: fill in %(fields)s.", device=line.display_name, fields=", ".join(missing)))
            if line.warranty_classification == 'no_fault_found':
                next_state = 'qc_testing'
            elif line.is_chargeable:
                next_state = 'quoted'
            else:
                next_state = 'in_repair'
            line.write({'state': next_state, 'diagnostic_date': fields.Datetime.now()})
            line.lot_id.sudo().warranty_classification = line.warranty_classification
            line.rma_id.message_post(body=self.env._(
                "Technical inspection of %(device)s: %(classification)s -> %(state)s",
                device=line.display_name,
                classification=dict(WARRANTY_CLASSIFICATION)[line.warranty_classification],
                state=dict(LINE_STATES)[next_state],
            ))
        self.rma_id._update_processing_state()
        return True

    def _set_po_pending(self):
        """Called once the dealer approved the quotation: work waits for the PO number."""
        lines = self.filtered(lambda line: line.state == 'quoted')
        lines.state = 'po_pending'
        for rma in lines.rma_id:
            if rma.po_number:
                rma.action_submit_po(rma.po_number)
            elif not rma.po_pending_since:
                rma.po_pending_since = fields.Datetime.now()
        return lines

    def action_reject(self, reason):
        reason = (reason or '').strip()
        if not reason:
            raise UserError(self.env._("A reason is mandatory to reject a device."))
        for line in self:
            if line.state not in ('inspected', 'quoted', 'po_pending'):
                raise UserError(self.env._("%s can no longer be rejected.", line.display_name))
            line.write({
                'state': 'rejected',
                'rejection_reason': reason,
                'final_test_result': 'pending',
                'quality_check': 'pending',
            })
            line.rma_id.message_post(body=self.env._(
                "%(device)s rejected / return as-is. Reason: %(reason)s", device=line.display_name, reason=reason))
        return True

    def action_complete_repair(self):
        for line in self:
            if line.state != 'in_repair':
                raise UserError(self.env._("%s is not in repair.", line.display_name))
            if not line.repair_work_done:
                raise UserError(self.env._("%s: describe the repair work done.", line.display_name))
            line.write({
                'state': 'qc_testing',
                'repair_date': line.repair_date or fields.Date.context_today(line),
            })
        self._consume_spare_parts()
        return True

    def action_qc_validate(self):
        """Final test + quality check both passed -> device ready for dispatch."""
        for line in self:
            if line.state != 'qc_testing':
                raise UserError(self.env._("%s is not awaiting quality check.", line.display_name))
            if line.final_test_result == 'failed' or line.quality_check == 'failed':
                line.write({'state': 'in_repair', 'final_test_result': 'pending', 'quality_check': 'pending'})
                line.rma_id.message_post(body=self.env._("%s failed QC and was sent back to repair.", line.display_name))
                continue
            if line.final_test_result != 'passed' or line.quality_check != 'passed':
                raise UserError(self.env._(
                    "%s: record a passed Final Test Result and Quality Check.", line.display_name))
            line.write({
                'state': 'ready',
                'quality_check_user_id': line.quality_check_user_id.id or self.env.user.id,
                'quality_check_date': fields.Datetime.now(),
            })
            line._update_serial_history()
        return True

    def _update_serial_history(self):
        for line in self:
            line.lot_id.sudo().write({
                'last_repair_date': line.repair_date or fields.Date.context_today(line),
                'last_rma_number': line.rma_id.name,
            })

    def _consume_spare_parts(self):
        self.part_line_ids._consume()
