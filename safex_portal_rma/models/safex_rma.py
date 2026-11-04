from odoo import models


class SafexRma(models.Model):
    _name = 'safex.rma'
    _inherit = ['safex.rma', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for rma in self:
            rma.access_url = f'/my/rma/{rma.id}'


class SafexRmaLine(models.Model):
    _inherit = 'safex.rma.line'

    def _get_portal_state_label(self):
        """Device status as worded for the dealer (internal step names mean little to them)."""
        self.ensure_one()
        labels = {
            'draft': self.env._("Awaiting Receipt") if self.rma_id.state != 'draft' else self.env._("Draft"),
            'inspected': self.env._("Under Inspection"),
            'quoted': self.env._("Awaiting Your Approval"),
            'po_pending': self.env._("Awaiting Your PO"),
            'in_repair': self.env._("In Repair"),
            'qc_testing': self.env._("Final Testing"),
            'ready': self.env._("Ready for Dispatch"),
            'rejected': self.env._("Returned As-Is"),
        }
        if self.state == 'draft' and self.rma_id.state == 'received':
            return self.env._("Received - Awaiting Inspection")
        return labels.get(self.state, self.state)
