from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_safex_document_company(self):
        """Branding company printed on an invoice of RMA repairs (CR-05), see
        sale.order._get_safex_document_company. Empty for other invoices."""
        self.ensure_one()
        company = self.company_id.sudo()
        if not company.safex_document_company_id:
            return self.env['res.company']
        orders = self.sudo().invoice_line_ids.sale_line_ids.order_id
        if any(orders.mapped('rma_id')):
            return company.safex_document_company_id
        return self.env['res.company']
