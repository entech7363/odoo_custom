from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    po_reapproval_enabled = fields.Boolean(
        string='Re-approve Edited Purchase Orders',
        default=True,
        help="When the lines of a purchase order are changed after it has entered "
             "the approval chain, restart that chain from the first step. "
             "Configured per company, like the approval steps themselves.",
    )
