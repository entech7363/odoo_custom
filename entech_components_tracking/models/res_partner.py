from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_type = fields.Selection(
        selection=[
            ('customer', 'Customer'),
            ('vendor', 'Vendor')
        ],
        string='Partner Type',
        default='customer'
    )
    serial_number = fields.Char(string="Serial Number", readonly=True)


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:

            if 'partner_type' not in vals:
                vals['partner_type'] = self.env.context.get('default_partner_type', 'customer')


            if not vals.get('serial_number'):
                if vals.get('partner_type') == 'customer':
                    vals['serial_number'] = self.env['ir.sequence'].next_by_code('res.partner.customer')
                elif vals.get('partner_type') == 'vendor':
                    vals['serial_number'] = self.env['ir.sequence'].next_by_code('res.partner.vendor')

        return super().create(vals_list)





