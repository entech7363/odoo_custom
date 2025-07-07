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
    battery_sno = fields.Char(string="Battery_SNO")
    docking_station_sno = fields.Char(string="Docking_Station_SNO")
    # show_battery = fields.Boolean(compute='_compute_show_serial_field', store=False)
    # show_docking_station = fields.Boolean(compute='_compute_show_serial_field', store=False)
    #
    # @api.depends('product_id')
    # def _compute_show_serial_field(self):
    #     for line in self:
    #         tmpl = line.product_id.product_tmpl_id
    #         components = tmpl.component_ids if tmpl else []
    #         line.show_battery = any(c.is_battery and c.serial_number for c in components)
    #         line.show_docking_station = any(c.is_docking_station and c.serial_number for c in components)


    show_vendor_warranty = fields.Boolean(compute='_compute_show_warranty_flags', store=False)
    show_customer_warranty = fields.Boolean(compute='_compute_show_warranty_flags', store=False)

    @api.depends('picking_type_id.code')
    def _compute_show_warranty_flags(self):
        for move in self:
            move_type = move.picking_type_id.code if move.picking_type_id else ''
            move.show_vendor_warranty = move_type == 'incoming'
            move.show_customer_warranty = move_type == 'outgoing'

    def action_transfer_serial_fields(self):
        for move in self:
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


            existing_line = move.move_line_ids.filtered(lambda l: not l.lot_id and l.qty_done == 0.0)

            line_vals = {
                'product_id': move.product_id.id,
                'lot_id': lot.id,
                'qty_done': 1.0,
                'lot_name': move.serial_no,
                'imei_no_1': move.imei_no_1,
                'imei_no_2': move.imei_no_2,
                'battery_sno': move.battery_sno,
                'docking_station_sno': move.docking_station_sno,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
            }

            if existing_line:
                existing_line[0].write(line_vals)
            else:
                line_vals['move_id'] = move.id
                self.env['stock.move.line'].create(line_vals)


            move.serial_no = False
            move.imei_no_1 = False
            move.imei_no_2 = False
            move.battery_sno = False
            move.docking_station_sno = False
