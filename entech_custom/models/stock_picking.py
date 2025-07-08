from odoo import models, fields

class DeliveryOrder(models.Model):
    _inherit = 'stock.picking'
    sale_id=fields.Many2one('sale.order', string="Sale Order")



    #Customer_RFQ = fields.Char(string="Customer RFQ", related="sale_id.Customer_RFQ")
    #Customer_RFQ_date = fields.Date(string="Customer RFQ Date", related="sale_id.Customer_RFQ_date")
    Customer_Purchase = fields.Char(string="PO Number", related="sale_id.Customer_Purchase")
    Customer_Purchase_date = fields.Date(string="PO Date", related="sale_id.Customer_Purchase_date")
    Customer_Delivery = fields.Char(string="Place of Delivery", related="sale_id.Customer_Delivery")
    #Customer_Number = fields.Char(string="Customer Number",related="sale_id.Customer_Number")

class ReceiptPurchase(models.Model):
    _inherit = "stock.picking"

    purchase_id = fields.Many2one('purchase.order', string="Purchase")

    Quotation_number = fields.Char(string="Quotation Number", related="purchase_id.Quotation_number")
    Quotation_date = fields.Date(string="Quotation Date", related="purchase_id.Quotation_date")
    Order_Number = fields.Char(string=" Order Number", related="purchase_id.Order_Number")
    Order_Date = fields.Date(string="Order Date", related="purchase_id.Order_Date")
    Reference_Number = fields.Char(string="Reference Number", related="purchase_id.Reference_Number")
    Delivery_Type = fields.Char(string="Delivery Type", related="purchase_id.Delivery_Type")
    Receipt_Number = fields.Char(string="Receipt Number", related="purchase_id.Receipt_Number")






