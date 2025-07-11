from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    Customer_RFQ = fields.Char(string="RFQ NO")
    Customer_RFQ_date = fields.Date(string="RFQ Date")
    Customer_Purchase = fields.Char(string="PO Number")
    Customer_Purchase_date = fields.Date(string="PO Date")
    Customer_Delivery = fields.Char(string="Place of Delivery")
    #Customer_Number = fields.Char(string="Customer Number")
    For_Company=fields.Char(string="Company Name")



