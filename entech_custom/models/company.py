from odoo import models, api, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    # _check_company_auto = True
    #
    # categ_id = fields.Many2one(
    #     check_company=True,
    # )

    @api.model
    def create(self, vals):
        user = self.env.user
        if len(user.company_ids) == 1 and not vals.get('company_id'):
            vals['company_id'] = user.company_id.id
        return super(ProductTemplate, self).create(vals)



