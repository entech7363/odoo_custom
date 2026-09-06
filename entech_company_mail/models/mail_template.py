# -*- coding: utf-8 -*-
from odoo import models

class MailTemplate(models.Model):
    _inherit = 'mail.template'

    def _generate_template(self, res_ids, render_fields, find_or_create_partners=False):
        """Force the company email on template-driven sends (automated actions,
        crons, ``template.send_mail()``)."""
        results = super()._generate_template(
            res_ids, render_fields, find_or_create_partners=find_or_create_partners
        )
        if 'email_from' not in render_fields or not self.model or not res_ids:
            return results

        Model = self.env.get(self.model)
        if Model is None or 'company_id' not in Model._fields:
            return results

        for record in Model.browse(res_ids):
            email_from = record.company_id._entech_email_from_for_model(self.model)
            if email_from and record.id in results:
                results[record.id]['email_from'] = email_from

        return results
