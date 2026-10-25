from odoo import api, fields, models

from odoo.addons.safex_warranty_core.models.stock_lot import WARRANTY_CLASSIFICATION


class SafexInspectionItem(models.Model):
    """One line of the physical inspection checklist (DES00108), e.g. "Display / Front Glass"."""
    _name = 'safex.inspection.item'
    _description = "SafeX Inspection Checklist Item"
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    required = fields.Boolean(
        default=True, help="The inspector must pick an option before validating the physical inspection.")
    option_ids = fields.One2many('safex.inspection.option', 'item_id', string="Options", copy=True)
    default_option_id = fields.Many2one(
        'safex.inspection.option', compute='_compute_default_option_id',
        help="Option pre-filled on new devices.")

    @api.depends('option_ids.is_default', 'option_ids.sequence')
    def _compute_default_option_id(self):
        for item in self:
            item.default_option_id = item.option_ids.filtered('is_default')[:1]

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        self.env['safex.rma.line'].search([('state', '=', 'draft')])._sync_inspection_lines()
        return items

    def write(self, vals):
        res = super().write(vals)
        if vals.get('active'):
            self.env['safex.rma.line'].search([('state', '=', 'draft')])._sync_inspection_lines()
        return res


class SafexInspectionOption(models.Model):
    """A possible answer for a checklist item, e.g. "Cracked"."""
    _name = 'safex.inspection.option'
    _description = "SafeX Inspection Checklist Option"
    _order = 'sequence, id'

    item_id = fields.Many2one('safex.inspection.item', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    requires_photo = fields.Boolean(
        string="Damage - Photo Required",
        help="Choosing this option marks the device as physically damaged: at least one inspection "
             "photo is required to validate the physical inspection.")
    suggested_classification = fields.Selection(
        WARRANTY_CLASSIFICATION,
        help="Pre-filled warranty classification when this option is chosen and the device has none yet. "
             "The technician can still change it at technical inspection.")
    is_default = fields.Boolean(string="Default", help="Pre-filled on new devices.")

    @api.depends('item_id', 'name')
    def _compute_display_name(self):
        for option in self:
            option.display_name = option.name or ''


class SafexRmaLineInspection(models.Model):
    """The answer recorded for one checklist item on one device."""
    _name = 'safex.rma.line.inspection'
    _description = "SafeX Device Inspection Result"
    _order = 'sequence, id'
    _check_company_auto = True

    rma_line_id = fields.Many2one('safex.rma.line', string="Device", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='rma_line_id.company_id', store=True)
    item_id = fields.Many2one('safex.inspection.item', string="Checklist Item", required=True, ondelete='restrict')
    sequence = fields.Integer(related='item_id.sequence', store=True)
    required = fields.Boolean(related='item_id.required')
    option_id = fields.Many2one(
        'safex.inspection.option', string="Condition", ondelete='restrict',
        domain="[('item_id', '=', item_id)]")
    requires_photo = fields.Boolean(related='option_id.requires_photo')
    notes = fields.Char()

    _sql_constraints = [
        ('unique_item_per_device', 'UNIQUE(rma_line_id, item_id)',
         "Each checklist item can only be recorded once per device."),
    ]
