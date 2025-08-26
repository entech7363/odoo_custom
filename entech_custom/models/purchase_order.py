from odoo import models, fields

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    Quotation_number = fields.Char(string="Quotation Number")
    Quotation_date = fields.Date(string="Quotation Date")
    Order_Number = fields.Char(string="Our Ref")
    Order_Date = fields.Date(string="Order Date")
    Customer_Delivery = fields.Char(string="Place of Delivery")
    #Reference_Number = fields.Char(string="Reference Number")
    #Delivery_Type = fields.Char(string="Delivery Type")
    #Receipt_Number = fields.Char(string="Receipt Number")

