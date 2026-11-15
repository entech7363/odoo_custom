from odoo import fields, models
from odoo.exceptions import UserError


class SafexRma(models.Model):
    _inherit = 'safex.rma'

    inspection_report_sent_date = fields.Datetime(
        string="Inspection Report Sent On", readonly=True, copy=False, tracking=True)

    def _send_rma_template(self, xmlid, attachments_by_rma=None):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            return
        for rma in self:
            attachments = (attachments_by_rma or {}).get(rma.id, self.env['ir.attachment'])
            # Passing attachment_ids (even empty) overrides the composer's own attachments, which
            # is where the template's report_template_ids PDFs are rendered: only pass extras.
            extra = {'attachment_ids': attachments.ids} if attachments else {}
            rma.message_post_with_source(template, subtype_xmlid='mail.mt_comment', **extra)

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

    def action_confirm_receipt(self):
        res = super().action_confirm_receipt()
        self._send_rma_template('safex_rma_reports.mail_template_rma_received')
        return res

    def action_send_quotation(self):
        orders_by_rma = {rma.id: rma.sale_order_ids.filtered(lambda so: so.state == 'draft') for rma in self}
        res = super().action_send_quotation()
        attachments_by_rma = {rma.id: rma._render_quotation_attachments(orders_by_rma[rma.id]) for rma in self}
        self._send_rma_template('safex_rma_reports.mail_template_quotation_ready', attachments_by_rma)
        return res

    def action_send_inspection_report(self):
        """Staff send the inspection outcome (items received, discrepancies, spare parts that may be
        required) to the dealer, with the Inspection Report PDF (CR-12). The quotation stays a
        separate email."""
        for rma in self:
            if rma.state not in ('inspection', 'processing'):
                raise UserError(self.env._(
                    "%s: the inspection report can be sent once the physical inspection is complete.", rma.name))
        self._send_rma_template('safex_rma_reports.mail_template_inspection_report')
        self.inspection_report_sent_date = fields.Datetime.now()
        return True

    def action_dispatch(self):
        res = super().action_dispatch()
        self._send_rma_template('safex_rma_reports.mail_template_rma_dispatched')
        return res

    def _get_lines_by_product(self, lines=None):
        """[(product, devices)] keeping the first-appearance order: documents print the model once
        with each unit beneath it (CR-06)."""
        lines = self.line_ids if lines is None else lines
        groups = {}
        for line in lines:
            groups[line.product_id] = groups.get(line.product_id, line.browse()) | line
        return list(groups.items())

    def _get_report_received_lines(self):
        """Devices physically received (declared devices found in the carton and unexpected ones)."""
        return self.line_ids.filtered(lambda line: not line.not_received)

    def get_missing_accessory_labels(self, line):
        """Accessories declared by the dealer but not found in the carton (same rule as
        safex.rma.line accessory_discrepancy)."""
        missing = [label for key, label in self._get_accessory_label_map().items()
                   if line[f'acc_declared_{key}'] and not line[f'acc_received_{key}']]
        if line.acc_declared_other and not line.acc_received_other:
            missing.append(line.acc_declared_other)
        return missing

    def get_received_accessory_details(self, line):
        """Received accessories, with the battery / docking station serial numbers (CR-03)."""
        serials = {
            'battery': line.acc_declared_battery_sno,
            'dock': line.acc_declared_dock_sno,
        }
        details = []
        for key, label in self._get_accessory_label_map().items():
            if not line[f'acc_received_{key}']:
                continue
            if serials.get(key):
                label = self.env._("%(accessory)s (S/N %(serial)s)", accessory=label, serial=serials[key])
            details.append(label)
        if line.acc_received_other:
            details.append(line.acc_received_other)
        return details

    def _get_accessory_label_map(self):
        return {
            'charger': self.env._("Charger"),
            'dock': self.env._("Docking Station"),
            'battery': self.env._("Battery"),
            'screwdriver': self.env._("Screwdriver"),
            'cable': self.env._("Cable"),
            'box': self.env._("Box"),
        }

    def get_accessory_labels(self, line, prefix):
        labels = self._get_accessory_label_map()
        result = [label for key, label in labels.items() if line[f'{prefix}_{key}']]
        if line[f'{prefix}_other']:
            result.append(line[f'{prefix}_other'])
        return result
