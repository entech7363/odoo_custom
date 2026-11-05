from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .product_template import SAFEX_ALLOWED_COMPANIES_HELP


class ProductCategory(models.Model):
    _inherit = 'product.category'

    safex_company_ids = fields.Many2many(
        'res.company', 'product_category_safex_company_rel', 'categ_id', 'company_id',
        string="Allowed Companies", help=SAFEX_ALLOWED_COMPANIES_HELP)

    @api.constrains('safex_company_ids')
    def _check_safex_company_ids(self):
        # product.category has no company_id in standard Odoo (entech_custom adds one).
        if 'company_id' not in self._fields:
            return
        for category in self:
            if category.company_id and category.safex_company_ids \
                    and category.company_id not in category.safex_company_ids:
                raise ValidationError(self.env._(
                    "Category %(category)s: its company %(company)s must be one of its Allowed Companies.",
                    category=category.display_name, company=category.company_id.name))

    def write(self, vals):
        res = super().write(vals)
        # company_id is not a declared dependency of the constraint (it only exists with entech_custom).
        if 'company_id' in vals:
            self._check_safex_company_ids()
        return res
