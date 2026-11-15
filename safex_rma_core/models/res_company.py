from odoo import fields, models


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
