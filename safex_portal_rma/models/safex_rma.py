from odoo import models


class SafexRma(models.Model):
    _name = 'safex.rma'
    _inherit = ['safex.rma', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for rma in self:
            rma.access_url = f'/my/rma/{rma.id}'
