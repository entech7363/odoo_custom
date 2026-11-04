from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    safex_dealer_warranty_months = fields.Integer(
        string="Dealer Warranty (months)", default=16,
        help="Default SafeX dealer warranty, counted from the delivery to the dealer. "
             "A product can override it.")
    safex_factory_warranty_months = fields.Integer(
        string="Factory Warranty (months)", default=18,
        help="Default manufacturer warranty, counted from the GRN (receipt) date. "
             "A product can override it.")
    safex_enforce_dealer_warranty = fields.Boolean(
        string="Enforce Dealer Warranty on Deliveries",
        help="When a device is delivered to a dealer, always apply the SafeX dealer warranty "
             "(product override, else the company default) instead of the months typed on the delivery.")
