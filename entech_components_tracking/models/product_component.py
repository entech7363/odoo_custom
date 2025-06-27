from odoo import models, fields, api

class ProductComponent(models.Model):
    _name = 'product.component'
    _description = 'Product Component'

    product_part_id = fields.Many2one('product.part', string='Product Part')
    serial_number = fields.Boolean(string='Serial No')
    vendor_warranty = fields.Integer(string='Vendor Warranty')
    customer_warranty = fields.Integer(string='Customer Warranty')
    product_tmpl_id = fields.Many2one('product.template', string='Product Template')

    is_battery = fields.Boolean(string='Is Battery')
    is_docking_station = fields.Boolean(string='Is Docking Station')

    @api.onchange('is_battery')
    def _onchange_is_battery(self):
        if self.is_battery:
            self.is_docking_station = False

    @api.onchange('is_docking_station')
    def _onchange_is_docking_station(self):
        if self.is_docking_station:
            self.is_battery = False
