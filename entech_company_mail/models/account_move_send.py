# -*- coding: utf-8 -*-
from odoo import api, models

class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _get_mail_default_field_value_from_template(self, mail_template, lang, move, field, **kwargs):
        """Force the company email on the "Send & Print" flow.

        Invoices are not sent through ``mail.compose.message``: ``_send_mails()``
        takes ``email_from`` from this helper, which renders the template field
        (usually the salesperson). Overriding here also covers the case where no
        template is set, which would otherwise fall back on the current user.
        """
        if field == 'email_from':
            email_from = move.company_id._entech_email_from_for_model('account.move')
            if email_from:
                return email_from
        return super()._get_mail_default_field_value_from_template(
            mail_template, lang, move, field, **kwargs
        )
