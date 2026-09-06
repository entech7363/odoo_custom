# -*- coding: utf-8 -*-
from odoo import api, models

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _entech_email_from_for_records(self, res_ids):
        """Company sender shared by every record in ``res_ids``.

        Returns ``False`` when the model is not covered, the toggle is off, or
        the records span companies with different senders (each record is then
        fixed individually in ``_prepare_mail_values_dynamic``).
        """
        self.ensure_one()
        if not self.model or self.model not in self.env or not res_ids:
            return False
        Model = self.env[self.model]
        if 'company_id' not in Model._fields:
            return False
        emails_from = {
            record.company_id._entech_email_from_for_model(self.model)
            for record in Model.browse(res_ids).exists()
        }
        if len(emails_from) != 1:
            return False
        return emails_from.pop()

    @api.depends('composition_mode', 'email_from', 'model', 'res_domain', 'res_ids', 'template_id')
    def _compute_authorship(self):
        """Show the company email in the composer's From field.

        Core resets ``email_from`` to the current user; re-apply the company
        sender afterwards so the user can see it before sending.
        """
        super()._compute_authorship()
        for composer in self:
            email_from = composer._entech_email_from_for_records(composer._evaluate_res_ids())
            if email_from:
                composer.email_from = email_from

    def _prepare_mail_values_dynamic(self, res_ids):
        """Per-record sender for batch and mass-mail sends.

        This path renders ``email_from`` from the composer, which is a single
        value for the whole batch, so records of other companies would keep the
        wrong sender without this override.
        """
        mail_values_all = super()._prepare_mail_values_dynamic(res_ids)
        if not self.model or self.model not in self.env:
            return mail_values_all
        Model = self.env[self.model]
        if 'company_id' not in Model._fields:
            return mail_values_all

        for record in Model.browse(res_ids):
            email_from = record.company_id._entech_email_from_for_model(self.model)
            if email_from and record.id in mail_values_all:
                mail_values_all[record.id]['email_from'] = email_from

        return mail_values_all
