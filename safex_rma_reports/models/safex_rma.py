from odoo import models


class SafexRma(models.Model):
    _inherit = 'safex.rma'

    def _send_rma_template(self, xmlid, attachments_by_rma=None):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            return
        for rma in self:
            attachments = (attachments_by_rma or {}).get(rma.id, self.env['ir.attachment'])
            rma.message_post_with_source(
                template, subtype_xmlid='mail.mt_comment', attachment_ids=attachments.ids)

    def _render_quotation_attachments(self, orders):
        attachments = self.env['ir.attachment']
        for order in orders:
            pdf, _ = self.env['ir.actions.report']._render_qweb_pdf(
                'safex_rma_reports.action_report_sectioned_repair_quotation', order.ids)
            attachments |= self.env['ir.attachment'].create({
                'name': self.env._("Repair Quotation - %s.pdf", order.name),
                'raw': pdf,
                'mimetype': 'application/pdf',
                'res_model': 'safex.rma',
                'res_id': self.id,
            })
        return attachments

    def action_submit(self):
        res = super().action_submit()
        self._send_rma_template('safex_rma_reports.mail_template_rma_submitted')
        return res

    def action_send_quotation(self):
        orders_by_rma = {rma.id: rma.sale_order_ids.filtered(lambda so: so.state == 'draft') for rma in self}
        res = super().action_send_quotation()
        attachments_by_rma = {rma.id: rma._render_quotation_attachments(orders_by_rma[rma.id]) for rma in self}
        self._send_rma_template('safex_rma_reports.mail_template_quotation_ready', attachments_by_rma)
        return res

    def action_dispatch(self):
        res = super().action_dispatch()
        self._send_rma_template('safex_rma_reports.mail_template_rma_dispatched')
        return res

    def get_accessory_labels(self, line, prefix):
        labels = {
            'charger': self.env._("Charger"),
            'dock': self.env._("Docking Station"),
            'battery': self.env._("Battery"),
            'screwdriver': self.env._("Screwdriver"),
            'cable': self.env._("Cable"),
            'box': self.env._("Box"),
        }
        result = [label for key, label in labels.items() if line[f'{prefix}_{key}']]
        if line[f'{prefix}_other']:
            result.append(line[f'{prefix}_other'])
        return result
