#from odoo import models, fields, api

#class ApprovalSteps(models.Model):
    #_name = 'approval.steps'
    #_description = 'Approval Steps'

   # type = fields.Selection([('sale', 'Sale')], string='Type', required=True)
    #user_id = fields.Many2one('res.users', string='User',  required=True)
    #minimum_amount = fields.Monetary(string='Minimum Amount', currency_field='currency_id', required=True)
    #currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency', store=True, readonly=True)


   # @api.depends('minimum_amount')
    #def _compute_currency(self):
        #for record in self:
            #company = record.env.company
            #record.currency_id = company.currency_id

