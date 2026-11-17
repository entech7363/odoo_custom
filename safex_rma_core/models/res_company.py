from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    safex_rma_terms = fields.Html(
        string="RMA Terms & Conditions",
        help="Printed on every RMA reference document of this company.",
    )
    safex_document_company_id = fields.Many2one(
        'res.company', string="RMA Documents Branding Company",
        domain="[('partner_id.is_safex_internal_entity', '=', True)]",
        help="Letterhead, address and footer printed on the RMA documents of this company "
             "(e.g. SafeX Instruments Ltd (UK) for SafeX Qatar). Empty: this company's own branding.",
    )
    safex_rma_company_id = fields.Many2one(
        'res.company', string="RMAs Handled By",
        domain="[('partner_id.is_safex_internal_entity', '=', True), ('id', '!=', id)]",
        help="SafeX company that receives and processes the RMAs of the devices sold by this company "
             "(e.g. SafeX Qatar for SafeX UK): dealer RMAs are created in that company, and new RMAs "
             "default to it in the backend. Empty: this company handles its own RMAs.",
    )

    @api.constrains('safex_rma_company_id')
    def _check_safex_rma_company(self):
        for company in self.filtered('safex_rma_company_id'):
            if company.safex_rma_company_id.safex_rma_company_id:
                raise ValidationError(self.env._(
                    "%(handler)s itself hands its RMAs to another company: choose the company that handles "
                    "the RMAs directly.", handler=company.safex_rma_company_id.name))

    def _get_safex_rma_company(self):
        """Company in which the RMAs of this company's devices are created."""
        self.ensure_one()
        return self.sudo().safex_rma_company_id or self
