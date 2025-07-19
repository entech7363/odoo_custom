from odoo import models,fields,api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    margin_product = fields.Float(string='Margin of Product (%)',compute="_compute_margin_product",inverse="_inverse_margin_product",
                                  store=True)

    minimum_price = fields.Float(string='Minimum Sale Price',compute="_compute_minimum_price",inverse="_inverse_minimum_price",
                          store=True)


    @api.depends('standard_price', 'margin_product')
    def _compute_minimum_price(self):
        for record in self:
            if record.standard_price>0:
                record.minimum_price = record.standard_price *(1+record.margin_product / 100)
            #else:
                #record.minimum_price = 0.0


    def _inverse_minimum_price(self):
        for record in self:
            if record.standard_price:
                record.margin_product = ((record.minimum_price -record.standard_price)/record.standard_price)*100
            #else:
                #record.margin_product = 0.0

    @api.depends('standard_price', 'minimum_price')
    def _compute_margin_product(self):
        for record in self:
            if record.standard_price:
                record.margin_product = ((record.minimum_price - record.standard_price) / record.standard_price) * 100
            #else:
                #record.margin_product = 0

    def _inverse_margin_product(self):
        for record in self:
            if record.standard_price:
                record.minimum_price = record.standard_price*(1+record.margin_product/100)
            #else:
                #record.minimum_price = 0.0
