from odoo import models,fields
class InvoiceCreate(models.Model):
    _inherit = 'account.move'

    Customer_RFQ = fields.Char(string="Customer RFQ",compute='compute_sale_details')
    Customer_RFQ_date = fields.Date(string="Customer RFQ Date",compute='compute_sale_details')
    Customer_Purchase = fields.Char(string="PO Number",compute='compute_sale_details')
    Customer_Purchase_date = fields.Date(string=" PO Date",compute='compute_sale_details')
    Customer_Delivery = fields.Char(string="Place of Delivery",compute='compute_sale_details')
    #Customer_Number = fields.Char(string="Customer Number",compute='compute_sale_details')
    For_Company=fields.Char(string="Company Name",compute='compute_sale_details')

    def compute_sale_details(self):
        for k in self:
            order = k.line_ids.sale_line_ids.order_id[:1] or self.env['sale.order'].search([('name', '=', k.invoice_origin)], limit=1)
            if order:
                k.Customer_RFQ = order.Customer_RFQ
                k.Customer_RFQ_date = order.Customer_RFQ_date
                k.Customer_Purchase = order.Customer_Purchase
                k.Customer_Purchase_date = order.Customer_Purchase_date
                k.Customer_Delivery = order.Customer_Delivery
                #k.Customer_Number = order.Customer_Number
                k.For_Company = order.For_Company
                if order.incoterm and not k.invoice_incoterm_id:
                    k.invoice_incoterm_id = order.incoterm
                if order.incoterm_location and not k.incoterm_location:
                    k.incoterm_location = order.incoterm_location
            else:

                k.Customer_RFQ = ''
                k.Customer_RFQ_date = False
                k.Customer_Purchase = ''
                k.Customer_Purchase_date = False
                k.Customer_Delivery = ''
                #k.Customer_Number = ''
                k.For_Company = ''

class BillsCreate(models.Model):
    _inherit = 'account.move'

    Quotation_number = fields.Char(string="Quotation Number",compute='_compute_Quotation')
    Quotation_date = fields.Date(string="Quotation Date",compute='_compute_Quotation')
    Order_Number = fields.Char(string=" Order Number",compute='_compute_Quotation')
    Order_Date = fields.Date(string="Order Date",compute='_compute_Quotation')
    Customer_Delivery = fields.Char(string="Place of Delivery",compute='_compute_Quotation')
    #Reference_Number = fields.Char(string="Reference Number",compute='_compute_Quotation')
    #Delivery_Type = fields.Char(string="Delivery Type",compute='_compute_Quotation')
    #Receipt_Number = fields.Char(string="Receipt Number",compute='_compute_Quotation')
    def _compute_Quotation(self):
        for record in self:
            bill_new = record.line_ids.purchase_line_id.order_id[:1] or self.env['purchase.order'].search([('name', '=', record.invoice_origin)], limit=1)
            if bill_new:
                record.Quotation_number = bill_new.Quotation_number
                record.Quotation_date = bill_new.Quotation_date
                record.Order_Number = bill_new.Order_Number
                record.Order_Date = bill_new.Order_Date
                record.Customer_Delivery = bill_new.Customer_Delivery
                #record.Reference_Number=bill_new.Reference_Number
                #record.Delivery_Type=bill_new.Delivery_Type
                #record.Receipt_Number=bill_new.Receipt_Number
                if hasattr(bill_new, 'incoterm_id') and bill_new.incoterm_id and not record.invoice_incoterm_id:
                    record.invoice_incoterm_id = bill_new.incoterm_id
                if hasattr(bill_new, 'incoterm_location') and bill_new.incoterm_location and not record.incoterm_location:
                    record.incoterm_location = bill_new.incoterm_location
            else:
                record.Quotation_number = ''
                record.Quotation_date = False
                record.Order_Number = ''
                record.Order_Date = False
                record.Customer_Delivery = ''
                #record.Reference_Number=''
                #record.Delivery_Type=''
                #record.Receipt_Number=''










