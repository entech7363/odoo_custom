from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    report_header_image = fields.Binary(string="Header Image", attachment=False)
    report_footer_image = fields.Binary(string="Footer Image", attachment=False)
    purchase_terms=fields.Binary(string="Purchase Terms", attachment=False)

class BaseDocumentLayout(models.TransientModel):
    _inherit = "base.document.layout"

    report_header_image = fields.Binary(string="Header Image", attachment=False)
    report_footer_image = fields.Binary(string="Footer Image", attachment=False)
    purchase_terms = fields.Binary(string="Purchase Terms", attachment=False)

