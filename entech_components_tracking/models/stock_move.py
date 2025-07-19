from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo import _

class StockMove(models.Model):
    _inherit = 'stock.move'

    v_start_date = fields.Date(string="Vendor Start Date")
    vendor_warranty = fields.Integer(string='Vendor Warranty')
    c_start_date = fields.Date(string="Customer Start Date")
    customer_warranty = fields.Integer(string='Customer Warranty')

    serial_no = fields.Char(string="Serial No")
    imei_no_1 = fields.Char(string="IMEI NO.1")
    imei_no_2 = fields.Char(string="IMEI NO.2")
    battery_sno = fields.Char(string="Battery SNO")
    docking_station_sno = fields.Char(string="Docking Station SNO")


    show_battery = fields.Boolean(compute='_compute_show_serial_field', store=False)
    show_docking_station = fields.Boolean(compute='_compute_show_serial_field', store=False)

    show_battery_sno = fields.Boolean(compute='_compute_show_fields', default=True)
    show_docking_station_sno = fields.Boolean(compute='_compute_show_fields', default=True)

    show_imei_fields = fields.Boolean(compute='_compute_show_imei_fields', store=False)

    show_imei_form_fields = fields.Boolean(compute='_compute_show_imei_form_fields', store=False)

    show_vendor_warranty = fields.Boolean(compute='_compute_show_warranty_flags', store=False)
    show_customer_warranty = fields.Boolean(compute='_compute_show_warranty_flags', store=False)

    show_imei_fields = fields.Boolean(compute='_compute_show_imei_fields_conditional', store=True)
    show_battery_sno = fields.Boolean(compute='_compute_show_imei_fields_conditional', store=True)
    show_docking_station_sno = fields.Boolean(compute='_compute_show_imei_fields_conditional', store=True)

    @api.depends('product_id')
    def _compute_show_imei_fields_conditional(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            components = tmpl.component_ids if tmpl else []

            line.show_battery_sno = any(c.is_battery and c.serial_number for c in components)
            line.show_docking_station_sno = any(c.is_docking_station and c.serial_number for c in components)
            line.show_imei_fields = line.show_battery_sno or line.show_docking_station_sno


    # Dynamically show Battery and Docking Station fields in the form view
    @api.depends('product_id')
    def _compute_show_serial_field(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            components = tmpl.component_ids if tmpl else []
            line.show_battery = any(c.is_battery and c.serial_number for c in components)
            line.show_docking_station = any(c.is_docking_station and c.serial_number for c in components)

    # Dynamically show Battery and Docking Station fields in the list view
    @api.depends('product_id')
    def _compute_show_fields(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            components = tmpl.component_ids if tmpl else []
            line.show_battery_sno = any(c.is_battery and c.serial_number for c in components)
            line.show_docking_station_sno = any(c.is_docking_station and c.serial_number for c in components)

    # Dynamically show imeino1 and imeino2 in the list view
    @api.depends('product_id')
    def _compute_show_imei_fields(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            components = tmpl.component_ids if tmpl else []

            has_battery = any(c.is_battery and c.serial_number for c in components)
            has_docking = any(c.is_docking_station and c.serial_number for c in components)

            line.show_battery_sno = has_battery
            line.show_docking_station_sno = has_docking
            line.show_imei_fields = has_battery or has_docking

    # Dynamically show imeino1 and imeino2 in the form view
    @api.depends('product_id')
    def _compute_show_imei_form_fields(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            components = tmpl.component_ids if tmpl else []

            has_battery = any(c.is_battery and c.serial_number for c in components)
            has_docking = any(c.is_docking_station and c.serial_number for c in components)

            line.show_battery_sno = has_battery
            line.show_docking_station_sno = has_docking
            line.show_imei_form_fields = has_battery or has_docking

    @api.depends('picking_type_id.code')
    def _compute_show_warranty_flags(self):
        for move in self:
            move_type = move.picking_type_id.code if move.picking_type_id else ''
            move.show_vendor_warranty = move_type == 'incoming'
            move.show_customer_warranty = move_type == 'outgoing'

    def action_transfer_serial_fields(self):
        for move in self:
            # ✅ Validate all 5 serial-related fields are unique (if filled)
            values = [
                move.serial_no,
                move.imei_no_1,
                move.imei_no_2,
                move.battery_sno,
                move.docking_station_sno,
            ]
            non_empty_values = [v for v in values if v]
            if len(non_empty_values) != len(set(non_empty_values)):
                raise UserError(
                    _("All fields must have unique values."))

            if not move.serial_no:
                raise UserError(_("Please enter a Serial No."))

            lot = self.env['stock.lot'].search([
                ('name', '=', move.serial_no),
                ('product_id', '=', move.product_id.id)
            ], limit=1)

            if not lot:
                lot = self.env['stock.lot'].create({
                    'name': move.serial_no,
                    'product_id': move.product_id.id,
                    'company_id': move.company_id.id,
                })

            existing_line = move.move_line_ids.filtered(lambda l: l.lot_id == lot)
            if existing_line:
                raise UserError(_("Serial number '%s' is already assigned to this product.") % move.serial_no)

            if move.imei_no_1:
                if move.move_line_ids.filtered(lambda l: l.imei_no_1 == move.imei_no_1):
                    raise UserError(_("IMEI NO.1 '%s' already exists in another line.") % move.imei_no_1)

            if move.imei_no_2:
                if move.move_line_ids.filtered(lambda l: l.imei_no_2 == move.imei_no_2):
                    raise UserError(_("IMEI NO.2 '%s' already exists in another line.") % move.imei_no_2)

            if move.battery_sno:
                if move.move_line_ids.filtered(lambda l: l.battery_sno == move.battery_sno):
                    raise UserError(_("Battery SNO '%s' already exists in another line.") % move.battery_sno)

            if move.docking_station_sno:
                if move.move_line_ids.filtered(lambda l: l.docking_station_sno == move.docking_station_sno):
                    raise UserError(
                        _("Docking Station SNO '%s' already exists in another line.") % move.docking_station_sno)

            reusable_line = move.move_line_ids.filtered(lambda l: not l.lot_id)
            new_line_vals = {
                'product_id': move.product_id.id,
                'lot_id': lot.id,
                'lot_name': move.serial_no,
                'imei_no_1': move.imei_no_1,
                'imei_no_2': move.imei_no_2,
                'battery_sno': move.battery_sno,
                'docking_station_sno': move.docking_station_sno,
                'qty_done': 1.0,
            }

            if reusable_line:
                reusable_line[0].write(new_line_vals)
            else:
                new_line_vals['move_id'] = move.id
                self.env['stock.move.line'].create(new_line_vals)

            move.serial_no = False
            move.imei_no_1 = False
            move.imei_no_2 = False
            move.battery_sno = False
            move.docking_station_sno = False