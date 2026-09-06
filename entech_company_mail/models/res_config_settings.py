# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    email_from_company_sale = fields.Boolean(
        related='company_id.email_from_company_sale',
        readonly=False,
        string="Sales Emails from Company"
    )
    email_from_company_account = fields.Boolean(
        related='company_id.email_from_company_account',
        readonly=False,
        string="Invoice Emails from Company"
    )
    email_from_company_purchase = fields.Boolean(
        related='company_id.email_from_company_purchase',
        readonly=False,
        string="Purchase Emails from Company"
    )
    email_from_company_stock = fields.Boolean(
        related='company_id.email_from_company_stock',
        readonly=False,
        string="Delivery Emails from Company"
    )
