from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    safex_rma_terms = fields.Html(
        string="RMA Terms & Conditions",
        help="Printed on every RMA reference document of this company.",
    )
