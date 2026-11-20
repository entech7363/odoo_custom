# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools import str2bool


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _notify_by_email_prepare_rendering_context(self, message, msg_vals=False, model_description=False,
                                                     force_email_company=False, force_email_lang=False):
        """Settings -> Sales: ``Hide Quotation Email Button`` drops only the "View/Accept & Sign/Pay
        Quotation" button from quotation and order emails, for every company. ``has_button_access``
        is left untouched so the heading (quotation number) and the company footer, which the
        notification layout derives from it, still show as usual."""
        render_context = super()._notify_by_email_prepare_rendering_context(
            message, msg_vals=msg_vals, model_description=model_description,
            force_email_company=force_email_company, force_email_lang=force_email_lang,
        )
        param = self.env['ir.config_parameter'].sudo().get_param(
            'safex_hide_quotation_button.hide_quotation_email_button', 'False')
        render_context['safex_hide_quotation_button'] = str2bool(param, default=False)
        return render_context
