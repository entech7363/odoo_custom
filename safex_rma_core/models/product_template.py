from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_safex_spare_part = fields.Boolean(
        string="SafeX Spare Part",
        help="Component that can be consumed on an RMA repair (motherboard, screen, battery, seals...).",
    )
