from odoo import models, fields


class PurchaseApprovalHistory(models.Model):
    _name = 'purchase.approval.history'
    _description = 'Purchase Approval History'
    _order = 'revision, sequence'

    purchase_id = fields.Many2one('purchase.order', ondelete='cascade')
    step_id = fields.Many2one('approval.steps')
    user_id = fields.Many2one('res.users')
    date = fields.Datetime(default=fields.Datetime.now)
    sequence = fields.Integer()
    revision = fields.Integer(
        default=0,
        help="Approval round this signature belongs to. Incremented every time "
             "the order is sent back through the chain after being edited.",
    )
    active = fields.Boolean(
        default=True,
        help="Signatures from a superseded approval round are archived rather "
             "than deleted, so the audit trail is kept while reports and the "
             "order form only show the round currently in force.",
    )
