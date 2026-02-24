from odoo import models, fields, api

class PurchaseApprovalHistory(models.Model):
    _name = 'purchase.approval.history'
    _description = 'Purchase Approval History'

    purchase_id = fields.Many2one('purchase.order', ondelete='cascade')
    step_id = fields.Many2one('approval.steps')
    user_id = fields.Many2one('res.users')
    date = fields.Datetime(default=fields.Datetime.now)
    sequence = fields.Integer()
