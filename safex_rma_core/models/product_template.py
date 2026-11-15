from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_safex_spare_part = fields.Boolean(
        string="SafeX Spare Part",
        help="Component that can be consumed on an RMA repair (motherboard, screen, battery, seals...).",
    )
    safex_accessory_type = fields.Selection(
        [('battery', "Battery"), ('dock', "Docking Station")],
        string="SafeX Accessory Type",
        help="Spare battery / docking station stocked with its own serial numbers: the dealer portal "
             "accepts these serial numbers as declared accessories of a returned device.",
    )
