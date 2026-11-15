from odoo import fields, models


class SafexRmaPoVerify(models.TransientModel):
    """Staff type the PO number read on the PO document; it must match the dealer's number (CR-09)."""
    _name = 'safex.rma.po.verify'
    _description = "SafeX RMA: Verify PO"

    rma_id = fields.Many2one('safex.rma', string="RMA", required=True, readonly=True)
    dealer_po_number = fields.Char(related='rma_id.po_number', string="PO Number Entered by Dealer")
    # Documents of the current submission only: rejected earlier documents are not offered (CR-09).
    po_document_ids = fields.Many2many(related='rma_id.po_document_ids', string="PO Documents")
    po_number = fields.Char(string="PO Number on the Document", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.rma_id.action_verify_po(self.po_number)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}


class SafexRmaPoReject(models.TransientModel):
    _name = 'safex.rma.po.reject'
    _description = "SafeX RMA: Reject PO"

    rma_id = fields.Many2one('safex.rma', string="RMA", required=True, readonly=True)
    dealer_po_number = fields.Char(related='rma_id.po_number', string="PO Number Entered by Dealer")
    reason = fields.Text(required=True, help="Sent to the dealer, who can then submit a corrected PO on the portal.")

    def action_confirm(self):
        self.ensure_one()
        self.rma_id.action_reject_po(self.reason)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}
