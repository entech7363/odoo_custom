from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    imei_no_1 = fields.Char(string="IMEI NO.1")
    imei_no_2 = fields.Char(string="IMEI NO.2")
    battery_sno = fields.Char(string="Battery_SNO")
    docking_station_sno = fields.Char(string="Docking_Station_SNO")

    show_battery_sno = fields.Boolean(compute='_compute_show_serial_fields', store=False)
    show_docking_station_sno = fields.Boolean(compute='_compute_show_serial_fields', store=False)

    @api.depends('product_id')
    def _compute_show_serial_fields(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            components = tmpl.component_ids if tmpl else []
            line.show_battery_sno = any(c.is_battery and c.serial_number for c in components)
            line.show_docking_station_sno = any(c.is_docking_station and c.serial_number for c in components)

    def write(self, vals):
        res = super().write(vals)

        for line in self:
            lot = line.lot_id
            move = line.move_id
            picking_type = move.picking_type_id.code if move.picking_type_id else ''
            if lot and line.product_id:
                tmpl = line.product_id.product_tmpl_id
                components = tmpl.component_ids


                lot_values = {
                    'imei_no_1': line.imei_no_1,
                    'imei_no_2': line.imei_no_2,
                }

                if picking_type == 'incoming':
                    lot_values.update({
                        'v_start_date': move.v_start_date,
                        'vendor_warranty': move.vendor_warranty,
                    })

                if picking_type == 'outgoing':
                    lot_values.update({
                        'c_start_date': move.c_start_date,
                        'customer_warranty': move.customer_warranty,
                    })

                lot.write(lot_values)

                # battery
                if line.battery_sno:
                    battery_comp = components.filtered(lambda c: c.is_battery)
                    if battery_comp:
                        print("Battery:", battery_comp.product_part_id.name)
                        print("Vendor Warranty:", battery_comp.vendor_warranty)
                        print("Customer Warranty:", battery_comp.customer_warranty)

                        lot.lot_component_line_ids.filtered(
                            lambda l: l.product_part_id == battery_comp.product_part_id
                        ).unlink()
                        lot.lot_component_line_ids.create({
                            'lot_id': lot.id,
                            'product_part_id': battery_comp.product_part_id.id,
                            'serial_number': line.battery_sno,
                        })

                   #docking station
                if line.docking_station_sno:
                    dock_comp = components.filtered(lambda c: c.is_docking_station)
                    if dock_comp:
                        print("Docking Station:", dock_comp.product_part_id.name)
                        print("Vendor Warranty:", dock_comp.vendor_warranty)
                        print("Customer Warranty:", dock_comp.customer_warranty)

                        lot.lot_component_line_ids.filtered(
                            lambda l: l.product_part_id == dock_comp.product_part_id
                        ).unlink()
                        lot.lot_component_line_ids.create({
                            'lot_id': lot.id,
                            'product_part_id': dock_comp.product_part_id.id,
                            'serial_number': line.docking_station_sno,
                        })

        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for record in records:
            picking = record.picking_id
            lot = record.lot_id

            if picking.picking_type_code == 'outgoing' and lot:
                vals_to_write = {
                    'imei_no_1': lot.imei_no_1,
                    'imei_no_2': lot.imei_no_2,
                }

                for comp in lot.lot_component_line_ids:
                    product_part = comp.product_part_id


                    component = product_part and record.product_id.product_tmpl_id.component_ids.filtered(
                        lambda c: c.product_part_id.id == product_part.id
                    )

                    if component:
                        if component.is_battery:
                            vals_to_write['battery_sno'] = comp.serial_number
                        elif component.is_docking_station:
                            vals_to_write['docking_station_sno'] = comp.serial_number

                record.write(vals_to_write)

        return records
