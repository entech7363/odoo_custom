# -*- coding: utf-8 -*-
from odoo import fields, models

# Maps a mailed model to the per-company toggle deciding whether the company
# email must replace the user/salesperson email as sender.
EMAIL_FROM_COMPANY_FIELDS = {
    'sale.order': 'email_from_company_sale',
    'account.move': 'email_from_company_account',
    'purchase.order': 'email_from_company_purchase',
    'stock.picking': 'email_from_company_stock',
}

class ResCompany(models.Model):
    _inherit = 'res.company'

    email_from_company_sale = fields.Boolean(
        string="Sales Emails from Company",
        default=False,
        help="If enabled, outgoing quotation and sales order emails will use the company email as sender."
    )
    email_from_company_account = fields.Boolean(
        string="Invoice Emails from Company",
        default=False,
        help="If enabled, outgoing customer invoice and credit note emails will use the company email as sender."
    )
    email_from_company_purchase = fields.Boolean(
        string="Purchase Emails from Company",
        default=False,
        help="If enabled, outgoing RFQ and purchase order emails will use the company email as sender."
    )
    email_from_company_stock = fields.Boolean(
        string="Delivery Emails from Company",
        default=False,
        help="If enabled, outgoing delivery slip emails will use the company email as sender."
    )

    def _entech_email_from_for_model(self, model_name):
        """Sender to force for outgoing emails of ``model_name``.

        :return: the formatted company email when the matching toggle is on and
          the company has an email, ``False`` otherwise (keep standard sender).
        """
        field_name = EMAIL_FROM_COMPANY_FIELDS.get(model_name)
        if not field_name or not self:
            return False
        self.ensure_one()
        if not self[field_name]:
            return False
        return self.email_formatted or False
