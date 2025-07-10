from odoo import _, api, fields, models, tools

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sequence1 = fields.Integer(string='Sequence Number ')

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    sale_sequence_number = fields.Integer(string='No. ')
    
    @api.depends('sale_sequence_number')
    def _compute_sale_order_line_sequence(self):
        number = 1
        for record in self.order_id.order_line:
            record.sale_sequence_number = number
            number += 1
   
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    sequence1 = fields.Char(string=' Sequence Number')

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    purchase_sequence_number = fields.Integer(string='No.')

    @api.depends('purchase_sequence_number')
    def _compute_purchase_order_line_sequence(self):
        number = 1
        for record in self.order_id.order_line:
            record.purchase_sequence_number = number
            number += 1

class AccountMove(models.Model):
    _inherit = 'account.move'

    sequence1 = fields.Char(string='Sequence Number  ')

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    invoice_sequence_number = fields.Char(string='No.  ')

    @api.depends('invoice_sequence_number')
    def _compute_invoice_line_sequence(self):
        number = 1
        for record in self.move_id.invoice_line_ids:
            record.invoice_sequence_number = number
            number += 1



class StockMove(models.Model):
    _inherit = 'stock.move'

    stock_move_sequence = fields.Integer(string='No.', compute='_compute_stock_move_sequence', store=True)
    sequence1 = fields.Char(string='Sequence Number')
    mrp_sequence_no = fields.Integer(string='No.   ')
    @api.depends('sale_line_id.sale_sequence_number')
    def _compute_stock_move_sequence(self):
        for move in self:
            if move.sale_line_id:
                move.stock_move_sequence = move.sale_line_id.sale_sequence_number
            else:
                move.stock_move_sequence = False


    @api.depends('picking_id.move_ids_without_package')
    def _compute_stock_line_sequence(self):
        for picking in self.mapped('picking_id'):
            number = 1
            for move in picking.move_ids_without_package:
                move.stock_move_sequence = number
                number += 1




    @api.depends('mrp_sequence_no')
    def _compute_mrp_line_sequence(self):
        number = 1
        for record in self.raw_material_production_id.move_raw_ids:
            record.mrp_sequence_no = number
            number += 1
class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _get_aggregated_product_quantities(self, strict=False, except_package=False):
        res = super()._get_aggregated_product_quantities(strict=strict, except_package=except_package)

        # Group lines similarly as Odoo does, to find the source move line for each key
        def _group_key(line):
            return (
                line.product_id.id,
                line.product_uom_id.id,
                line.lot_id.id if strict else False,
                line.package_id.id if not except_package else False,
                line.result_package_id.id if not except_package else False,
                line.owner_id.id,
                line.location_id.id,
                line.location_dest_id.id,
                line.move_id.description_picking,
            )

        grouped_lines = {}
        for line in self:
            key = _group_key(line)
            if key not in grouped_lines:
                grouped_lines[key] = line  # Keep first line as reference

        for key, values in res.items():
            # key must exist in grouped_lines
            line = grouped_lines.get(key)
            if line:
                values['stock_move_sequence'] = line.move_id.stock_move_sequence or ''
            else:
                values['stock_move_sequence'] = ''

        return res
class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    sequence1 = fields.Char(string='Sequence Number')


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition.line'

    purchase_requistion_sequence = fields.Integer(string='No.',compute='_compute_purchase_requistion_sequence')

    @api.depends('purchase_requistion_sequence')
    def _compute_purchase_requistion_sequence(self):
        number = 1
        for record in self.requisition_id.line_ids:
            record.purchase_requistion_sequence = number
            number += 1


