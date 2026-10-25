from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    safex_quotation_terms = fields.Html(
        string="Repair Quotation Terms & Conditions",
        help="Copied into every RMA repair quotation of this company.",
    )
    safex_po_reminder_days = fields.Char(
        string="Reminder Days", default='7,14,30,40',
        help="Days after the dealer approved the quotation on which a PO reminder is emailed, "
             "e.g. 7,14,30,40.")

    @api.constrains('safex_po_reminder_days')
    def _check_safex_po_reminder_days(self):
        for company in self:
            try:
                company._get_safex_po_reminder_days()
            except ValueError:
                raise ValidationError(self.env._(
                    "Reminder Days must be positive whole numbers separated by commas, e.g. 7,14,30,40."))

    def _get_safex_po_reminder_days(self):
        self.ensure_one()
        days = sorted({int(day) for day in (self.safex_po_reminder_days or '').split(',') if day.strip()})
        if any(day <= 0 for day in days):
            raise ValueError
        return days
