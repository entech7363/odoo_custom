from odoo import models, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def create(self, vals):
        user = self.env.user
        if len(user.company_ids) == 1 and not vals.get('company_id'):
            vals['company_id'] = user.company_id.id
        return super(ProductTemplate, self).create(vals)
