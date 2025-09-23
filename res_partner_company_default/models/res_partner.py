from odoo import _, api, models,fields


class ResPartner(models.Model):
    _inherit = "res.partner"


    @api.model
    def create(self, vals):
        # If no company is set, assign the creator's company
        if not vals.get("company_id"):
            vals["company_id"] = self.env.company.id
        return super().create(vals)

