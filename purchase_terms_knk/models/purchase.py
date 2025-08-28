# -*- coding: utf-8 -*-
# Part of Kanak Infosystems LLP.
# See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    use_purchase_order_note = fields.Boolean(
        string='Default(s) Terms & Conditions', default=True)
    purchase_order_note = fields.Text(
        string='Default Term(s) and Condition(s)', translate=True)
    purchase_terms = fields.Html(string="Purchase terms")


class BaseDocumentLayout(models.TransientModel):
    _inherit = "base.document.layout"
    purchase_terms = fields.Html(string="Purchase terms")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    use_purchase_order_note = fields.Boolean(
        related='company_id.use_purchase_order_note', readonly=False,
        string='Default(s) Terms & Conditions')
    purchase_order_note = fields.Html(
        related='company_id.purchase_terms', readonly=False,
        string="Conditions &  Terms")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _default_default_note(self):
        for rec in self:

            if rec.company_id.use_purchase_order_note:
                rec.notes = rec.company_id.purchase_terms
            else:

                rec.notes = ''

    notes = fields.Html(
        string='Terms and Conditions',
        compute="_default_default_note")
