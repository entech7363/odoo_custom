from odoo import api, fields, models
from odoo.exceptions import UserError


class SafexRmaLinePart(models.Model):
    """Spare part required for / consumed by a device repair."""
    _name = 'safex.rma.line.part'
    _description = "SafeX RMA Spare Part"
    _check_company_auto = True

    rma_line_id = fields.Many2one('safex.rma.line', string="Device", required=True, ondelete='cascade', index=True)
    rma_id = fields.Many2one(related='rma_line_id.rma_id', store=True)
    company_id = fields.Many2one(related='rma_line_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', string="Spare Part", required=True, check_company=True,
        domain="[('is_safex_spare_part', '=', True)]")
    quantity = fields.Float(default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one(related='product_id.uom_id')
    location_id = fields.Many2one(
        'stock.location', string="Source Location", check_company=True,
        compute='_compute_location_id', store=True, readonly=False,
        domain="[('usage', '=', 'internal')]")
    cost_price = fields.Float(
        compute='_compute_cost_price', min_display_digits='Product Price', groups='base.group_user')
    local_stock_available = fields.Float(compute='_compute_local_stock_available', digits='Product Unit of Measure')
    stock_move_id = fields.Many2one('stock.move', readonly=True, copy=False)
    consumed = fields.Boolean(compute='_compute_consumed', store=True)

    @api.depends('company_id')
    def _compute_location_id(self):
        for part in self:
            if not part.location_id and part.company_id:
                warehouse = self.env['stock.warehouse'].search([('company_id', '=', part.company_id.id)], limit=1)
                part.location_id = warehouse.lot_stock_id

    @api.depends('product_id')
    def _compute_cost_price(self):
        for part in self:
            part.cost_price = part.product_id.with_company(part.company_id).standard_price

    @api.depends('product_id', 'location_id')
    def _compute_local_stock_available(self):
        for part in self:
            if part.product_id and part.location_id:
                part.local_stock_available = part.product_id.with_context(location=part.location_id.id).qty_available
            else:
                part.local_stock_available = 0.0

    @api.depends('stock_move_id.state')
    def _compute_consumed(self):
        for part in self:
            part.consumed = part.stock_move_id.state == 'done'

    def _consume(self):
        """Create and validate a stock move to the company's scrap/consumption location."""
        for part in self.filtered(lambda p: not p.consumed and p.quantity > 0):
            company = part.company_id
            dest = self.env['stock.location'].sudo().search([
                ('scrap_location', '=', True), ('company_id', 'in', (company.id, False)),
            ], order='company_id', limit=1)
            if not part.location_id or not dest:
                raise UserError(self.env._(
                    "Configure a source and a consumption location to consume %s.", part.product_id.display_name))
            move = self.env['stock.move'].sudo().create({
                'name': part.rma_line_id.display_name,
                'product_id': part.product_id.id,
                'product_uom': part.product_id.uom_id.id,
                'product_uom_qty': part.quantity,
                'company_id': company.id,
                'location_id': part.location_id.id,
                'location_dest_id': dest.id,
                'origin': part.rma_line_id.rma_id.name,
                'picked': True,
                'move_line_ids': [(0, 0, {
                    'product_id': part.product_id.id,
                    'product_uom_id': part.product_id.uom_id.id,
                    'quantity': part.quantity,
                    'location_id': part.location_id.id,
                    'location_dest_id': dest.id,
                    'company_id': company.id,
                })],
            })
            move._action_done()
            part.stock_move_id = move

    @api.depends('product_id', 'quantity')
    def _compute_display_name(self):
        for part in self:
            part.display_name = f"{part.product_id.display_name or ''} x {part.quantity:g}"
