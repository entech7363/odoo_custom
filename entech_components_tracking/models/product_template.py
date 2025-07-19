from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    component_ids = fields.One2many('product.component', 'product_tmpl_id', string='Components')
    vendor_part_no = fields.Char(string='Vendor Part No')


