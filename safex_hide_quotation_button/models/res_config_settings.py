# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hide_quotation_email_button = fields.Boolean(
        string="Hide Quotation Email Button",
        config_parameter='safex_hide_quotation_button.hide_quotation_email_button',
    )
