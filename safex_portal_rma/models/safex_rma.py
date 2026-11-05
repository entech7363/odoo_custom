from odoo import api, fields, models
from odoo.exceptions import UserError


class SafexRma(models.Model):
    _name = 'safex.rma'
    _inherit = ['safex.rma', 'portal.mixin']

    # Dealer acknowledgement of the returned shipment (portal "Confirm Receipt" button).
    # It is a record of the dealer's confirmation only: the RMA is still closed by SafeX.
    dealer_received_date = fields.Datetime(
        string="Received by Dealer On", readonly=True, copy=False, tracking=True)
    dealer_received_user_id = fields.Many2one(
        'res.users', string="Confirmed By", readonly=True, copy=False)
    # Badge shown next to the RMA status in the list (the status keeps its own "Received" = parcel at SafeX).
    dealer_receipt_status = fields.Selection(
        [('received', "Received by Dealer")], string="Dealer Receipt", compute='_compute_dealer_receipt_status')

    def _compute_access_url(self):
        super()._compute_access_url()
        for rma in self:
            rma.access_url = f'/my/rma/{rma.id}'

    @api.depends('dealer_received_date')
    def _compute_dealer_receipt_status(self):
        for rma in self:
            rma.dealer_receipt_status = 'received' if rma.dealer_received_date else False

    def action_dealer_confirm_receipt(self, user):
        """The dealer confirms on the portal that the dispatched devices arrived."""
        for rma in self:
            if rma.state not in ('dispatched', 'closed'):
                raise UserError(self.env._("Only a dispatched RMA can be confirmed as received."))
            if rma.dealer_received_date:
                continue
            rma.write({'dealer_received_date': fields.Datetime.now(), 'dealer_received_user_id': user.id})
            rma.message_post(
                body=self.env._("The dealer confirmed receipt of the dispatched devices."),
                author_id=user.partner_id.id)
        return True


class SafexRmaLine(models.Model):
    _inherit = 'safex.rma.line'

    def _get_portal_state_label(self):
        """Device status as worded for the dealer (internal step names mean little to them)."""
        self.ensure_one()
        rma = self.rma_id
        # Once the RMA has left SafeX, the device status follows the shipment.
        if rma.state in ('dispatched', 'closed') and self.state in ('ready', 'rejected'):
            if rma.dealer_received_date:
                return self.env._("Received")
            if self.state == 'rejected':
                return self.env._("Returned As-Is - Dispatched")
            return self.env._("Dispatched")
        labels = {
            'draft': self.env._("Awaiting Receipt") if rma.state != 'draft' else self.env._("Draft"),
            'inspected': self.env._("Under Inspection"),
            'quoted': self.env._("Awaiting Your Approval"),
            'po_pending': self.env._("Awaiting Your PO"),
            'in_repair': self.env._("In Repair"),
            'qc_testing': self.env._("Final Testing"),
            'ready': self.env._("Ready for Dispatch"),
            'rejected': self.env._("Returned As-Is"),
        }
        if self.state == 'draft' and rma.state == 'received':
            return self.env._("Received - Awaiting Inspection")
        return labels.get(self.state, self.state)
