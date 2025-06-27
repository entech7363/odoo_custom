from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    Customer_RFQ = fields.Char(string="Customer RFQ")
    Customer_RFQ_date = fields.Date(string="Customer RFQ Date")
    Customer_Purchase = fields.Char(string="Customer Purchase")
    Customer_Purchase_date = fields.Date(string="Customer Purchase Date")
    Customer_Delivery = fields.Char(string="Customer Delivery")
    Customer_Number = fields.Char(string="Customer Number")



