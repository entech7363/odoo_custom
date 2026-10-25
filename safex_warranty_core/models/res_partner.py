from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_safex_internal_entity = fields.Boolean(
        string="SafeX Internal Entity",
        help="SafeX group company (Qatar / UK). Deliveries to these partners are "
             "inter-company sales and are ignored when matching a device to a dealer.",
    )
    is_safex_dealer = fields.Boolean(
        string="SafeX Authorized Dealer",
        help="Authorized GCC channel partner eligible for the RMA dealer portal.",
    )
