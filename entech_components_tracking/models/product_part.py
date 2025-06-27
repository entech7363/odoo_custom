from odoo import models, fields, api

class ProductPart(models.Model):
    _name = 'product.part'
    _description = 'Product Part'

    name = fields.Char(string='Product Part', required=True)




