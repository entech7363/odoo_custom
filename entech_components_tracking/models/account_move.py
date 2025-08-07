from odoo import models, fields, api
from collections import defaultdict
from odoo.tools.misc import formatLang
from odoo.tools.float_utils import float_is_zero, float_compare


class AccountMove(models.Model):
   _inherit = 'account.move'


   def _get_invoiced_lot_values(self):
       print("HLOO")
       """ Get and prepare data to show a table of invoiced lot on the invoice's report. """
       self.ensure_one()
       res= []



       if self.state == 'draft' or not self.invoice_date or self.move_type not in ('out_invoice', 'out_refund'):
           return res

       current_invoice_amls = self.invoice_line_ids.filtered(lambda
                                                                 aml: aml.display_type == 'product' and aml.product_id and aml.product_id.type == 'consu' and aml.quantity)
       all_invoices_amls = current_invoice_amls.sale_line_ids.invoice_lines.filtered(
           lambda aml: aml._filter_aml_lot_valuation()).sorted(lambda aml: (aml.date, aml.move_name, aml.id))
       index = all_invoices_amls.ids.index(current_invoice_amls[:1].id) if current_invoice_amls[
                                                                           :1] in all_invoices_amls else 0
       previous_amls = all_invoices_amls[:index]
       invoiced_qties = current_invoice_amls._get_invoiced_qty_per_product()
       invoiced_products = invoiced_qties.keys()

       if self.move_type == 'out_invoice':
           # filter out the invoices that have been fully refund and re-invoice otherwise, the quantities would be
           # consumed by the reversed invoice and won't be print on the new draft invoice
           previous_amls = previous_amls.filtered(lambda aml: aml.move_id.payment_state != 'reversed')

       previous_qties_invoiced = previous_amls._get_invoiced_qty_per_product()

       if self.move_type == 'out_refund':
           # we swap the sign because it's a refund, and it would print negative number otherwise
           for p in previous_qties_invoiced:
               previous_qties_invoiced[p] = -previous_qties_invoiced[p]
           for p in invoiced_qties:
               invoiced_qties[p] = -invoiced_qties[p]

       qties_per_lot = defaultdict(float)
       previous_qties_delivered = defaultdict(float)
       stock_move_lines = current_invoice_amls.sale_line_ids.move_ids.move_line_ids.filtered(
           lambda sml: sml.state == 'done' and sml.lot_id).sorted(lambda sml: (sml.date, sml.id))
       for sml in stock_move_lines:
           if sml.product_id not in invoiced_products or not sml._should_show_lot_in_invoice():
               continue
           product = sml.product_id
           product_uom = product.uom_id
           quantity = sml.product_uom_id._compute_quantity(sml.quantity, product_uom)

           # is it a stock return considering the document type (should it be it thought of as positively or negatively?)
           is_stock_return = (
                   self.move_type == 'out_invoice' and (sml.location_id.usage, sml.location_dest_id.usage) == (
           'customer', 'internal')
                   or
                   self.move_type == 'out_refund' and (sml.location_id.usage, sml.location_dest_id.usage) == (
                   'internal', 'customer')
           )
           if is_stock_return:
               returned_qty = min(qties_per_lot[sml.lot_id], quantity)
               qties_per_lot[sml.lot_id] -= returned_qty
               quantity = returned_qty - quantity

           previous_qty_invoiced = previous_qties_invoiced[product]
           previous_qty_delivered = previous_qties_delivered[product]
           # If we return more than currently delivered (i.e., quantity < 0), we remove the surplus
           # from the previously delivered (and quantity becomes zero). If it's a delivery, we first
           # try to reach the previous_qty_invoiced
           if float_compare(quantity, 0, precision_rounding=product_uom.rounding) < 0 or \
                   float_compare(previous_qty_delivered, previous_qty_invoiced,
                                 precision_rounding=product_uom.rounding) < 0:
               previously_done = quantity if is_stock_return else min(previous_qty_invoiced - previous_qty_delivered,
                                                                      quantity)
               previous_qties_delivered[product] += previously_done
               quantity -= previously_done

           qties_per_lot[sml.lot_id] += quantity

       for lot, qty in qties_per_lot.items():
           # access the lot as a superuser in order to avoid an error
           # when a user prints an invoice without having the stock access
           lot = lot.sudo()
           if float_is_zero(invoiced_qties[lot.product_id], precision_rounding=lot.product_uom_id.rounding) \
                   or float_compare(qty, 0, precision_rounding=lot.product_uom_id.rounding) <= 0:
               continue
           invoiced_lot_qty = min(qty, invoiced_qties[lot.product_id])
           invoiced_qties[lot.product_id] -= invoiced_lot_qty

           battery_sno = ''
           docking_station_sno = ''
           for comp_line in lot.lot_component_line_ids:
               product_part = comp_line.product_part_id
               component = self.env['product.component'].search([
                   ('product_part_id', '=', product_part.id),
                   ('product_tmpl_id', '=', lot.product_id.product_tmpl_id.id)
               ], limit=1)

               if component:
                   if component.is_battery:
                       battery_sno = comp_line.serial_number
                   elif component.is_docking_station:
                       docking_station_sno = comp_line.serial_number

           #

           res.append({
               'product_name': lot.product_id.display_name,
               'quantity': formatLang(self.env, invoiced_lot_qty, dp='Product Unit of Measure'),
               'uom_name': lot.product_uom_id.name,
               'lot_name': lot.name,
               # The lot id is needed by localizations to inherit the method and add custom fields on the invoice's report.
               'lot_id': lot.id,
               'imei_no_1': lot.imei_no_1 if lot else '',
               'imei_no_2': lot.imei_no_2 if lot else '',
               'battery_sno': battery_sno,
               'docking_station_sno': docking_station_sno,
           })
           print("lot name:", lot.name)
           print("lot id:", lot.id)

       return res

   sale_order_date = fields.Datetime(string="Sale Order Date", compute="_compute_sale_order_date", store=False)

   @api.depends('invoice_origin')
   def _compute_sale_order_date(self):
       for record in self:
           sale_order = self.env['sale.order'].search([('name', '=', record.invoice_origin)], limit=1)
           record.sale_order_date = sale_order.date_order if sale_order else False



    # show_delivery_serials = fields.Boolean(string="Print Serial Numbers",)
    #
    # show_imei_columns = fields.Boolean(string="Show IMEI Columns", compute="_compute_show_imei_columns", store=False)
    #
    #
    #
    #
    # @api.depends('invoice_line_ids.imei_no_1', 'invoice_line_ids.imei_no_2',
    #              'invoice_line_ids.battery_sno', 'invoice_line_ids.docking_station_sno')
    # def _compute_show_imei_columns(self):
    #     for move in self:
    #         move.show_imei_columns = any(
    #             line.imei_no_1 or line.imei_no_2 or line.battery_sno or line.docking_station_sno
    #             for line in move.invoice_line_ids
    #         )
    #
    #
    #
