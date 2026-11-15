from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    safex_dealer_warranty_months = fields.Integer(
        string="Dealer Warranty (months)", groups='base.group_user',
        help="Leave 0 to use the company default.")
    safex_factory_warranty_months = fields.Integer(
        string="Factory Warranty (months)", groups='base.group_user',
        help="Leave 0 to use the company default.")


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _safex_dealer_warranty_months(self, company):
        return self.sudo().safex_dealer_warranty_months or company.safex_dealer_warranty_months

    def _safex_factory_warranty_months(self, company):
        return self.sudo().safex_factory_warranty_months or company.safex_factory_warranty_months
