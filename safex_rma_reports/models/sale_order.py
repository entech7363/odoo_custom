from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_safex_grouped_lines(self):
        """Order lines of an RMA quotation grouped for printing (CR-06):
        ([{'product': product, 'units': [{'device': rma line, 'lines': priced lines}]}], other lines).
        Units of the same model are printed under one model heading, whatever their order on the
        quotation. Presentation only: the order lines are not changed."""
        self.ensure_one()
        groups = {}
        units = {}
        others = self.order_line.browse()
        for line in self.order_line:
            device = line.rma_line_id
            if not device:
                if line.display_type != 'line_section':
                    others |= line
                continue
            if device not in units:
                units[device] = {'device': device, 'lines': line.browse()}
                groups.setdefault(device.product_id, {'product': device.product_id, 'units': []})
                groups[device.product_id]['units'].append(units[device])
            if not line.display_type:
                units[device]['lines'] |= line
        return list(groups.values()), others

    def _get_safex_document_company(self):
        """Branding company printed on the documents of an RMA quotation (letterhead, address and
        footer of e.g. SafeX UK for SafeX Qatar, CR-05). Empty for non-RMA orders and companies
        without a branding company: their documents keep the standard layout."""
        self.ensure_one()
        company = self.company_id.sudo()
        if self.rma_id and company.safex_document_company_id:
            return company.safex_document_company_id
        return self.env['res.company']
