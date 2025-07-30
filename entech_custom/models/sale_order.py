from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    Customer_RFQ = fields.Char(string="RFQ NO")
    Customer_RFQ_date = fields.Date(string="RFQ Date")
    Customer_Purchase = fields.Char(string="PO Number")
    Customer_Purchase_date = fields.Date(string="PO Date")
    Customer_Delivery = fields.Char(string="Place of Delivery")
    #Customer_Number = fields.Char(string="Customer Number")
    For_Company=fields.Char(string="Company Name")
    delivery_schedule = fields.Char(string='Delivery Schedule', default='0')
    # poc_name = fields.Char(string="POC")
    revision_number = fields.Integer(
        string="Revision Number",
        readonly=True,
        default=0,
        tracking=True
    )
    poc_id = fields.Many2one('res.partner', string='Point of Contact',
                             domain="[('parent_id', '=', partner_id), ('type', '=', 'contact')]")

    @api.onchange('partner_id')
    def _onchange_partner_id_set_poc(self):
        for order in self:
            if order.partner_id:
                if order.partner_id.type == 'contact' and order.partner_id.parent_id:

                    order.poc_id = order.partner_id
                else:

                    child_contact = self.env['res.partner'].search([
                        ('parent_id', '=', order.partner_id.id),
                        ('type', '=', 'contact')
                    ], limit=1)
                    order.poc_id = child_contact or False
            else:
                order.poc_id = False

    def write(self, vals):
        for order in self:
            if (order.state in ['draft', 'sent', 'to approve']
                    and not self._context.get('skip_revision_increment')
                    and 'revision_number' not in vals):
                super(SaleOrder, order).write(
                    dict(vals, revision_number=order.revision_number + 1)
                )
            else:
                super(SaleOrder, order).write(vals)
        return True








