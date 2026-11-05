from odoo import api, fields, models
from odoo.exceptions import ValidationError

SAFEX_ALLOWED_COMPANIES_HELP = (
    "Visible only in these companies. Leave empty to use the normal Odoo company rules.\n"
    "SafeX shared devices: leave Company empty (the serial numbers are then shared, the same "
    "serial record is used by every allowed company) and select the SafeX entities here.")


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    safex_dealer_warranty_months = fields.Integer(
        string="Dealer Warranty (months)", groups='base.group_user',
        help="Leave 0 to use the company default.")
    safex_factory_warranty_months = fields.Integer(
        string="Factory Warranty (months)", groups='base.group_user',
        help="Leave 0 to use the company default.")
    safex_company_ids = fields.Many2many(
        'res.company', 'product_template_safex_company_rel', 'product_tmpl_id', 'company_id',
        string="Allowed Companies", help=SAFEX_ALLOWED_COMPANIES_HELP)

    @api.constrains('company_id', 'safex_company_ids')
    def _check_safex_company_ids(self):
        for template in self:
            if template.company_id and template.safex_company_ids \
                    and template.company_id not in template.safex_company_ids:
                raise ValidationError(self.env._(
                    "Product %(product)s: its company %(company)s must be one of its Allowed Companies.",
                    product=template.display_name, company=template.company_id.name))

    def _safex_is_shared_device(self):
        """Shared SafeX device: no company (shared serials) and restricted to SafeX entities."""
        self.ensure_one()
        template = self.sudo()
        return not template.company_id and any(
            company.partner_id.is_safex_internal_entity for company in template.safex_company_ids)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _safex_dealer_warranty_months(self, company):
        return self.sudo().safex_dealer_warranty_months or company.safex_dealer_warranty_months

    def _safex_factory_warranty_months(self, company):
        return self.sudo().safex_factory_warranty_months or company.safex_factory_warranty_months
